import base64
import re, json

# from django.contrib.auth.models import User

from django.conf import settings
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.views import View
from django_redis import get_redis_connection
from .models import User, Address
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseServerError
from xiaoyu_mall.utils.response_code import RETCODE
from django.shortcuts import render, redirect, reverse
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from xiaoyu_mall.utils.views import LoginRequiredJSONMixin
import logging
from celery_tasks.email.tasks import send_verify_email
from users.utils import generate_verify_email_url, check_verify_email_token
from users import constants
from carts.utils import merge_carts_cookies_redis

logger = logging.getLogger('django')

from goods.models import SKU
from orders.models import OrderInfo
from django.core.paginator import Paginator, EmptyPage
from django.http import HttpResponseNotFound


class CartsSimpleView(View):
    """商品页面右上角购物车"""
    def get(self, request):
        user = request.user
        if user.is_authenticated:
             #用户已登录，查询Redis购物车
            redis_conn = get_redis_connection('carts')
            redis_cart = redis_conn.hgetall('carts_%s' % user.id)
            cart_selected = redis_conn.smembers('selected_s%' % user.id)
#             将redis中的两个数据统一格式，和Cookie中的格式一致，方便统一查询
            cart_dict = {}
            for sku_id, count in redis_cart.items():
                cart_dict[int(sku_id)] = {
                    'count':int(count),
                    'selected': sku_id in cart_selected
                }
        else:
                 #用户未登录
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                cart_dict = { }
                #构造简单购物车JSON数据
            cart_skus = []
            sku_ids = cart_dict.keys()
            skus = models.SKU.objects.filter(id_in=sku_ids)
            for sku in skus:
                cart_skus.append({
                    'id':sku.id,
                    'name':sku.name,
                    'count':cart_dict.get(sku.id).get('count'),
                    'default_image_url': settings.STATIC_URL + 'image/goods/' + sku.default_image.url + '.jpg',
                })
            return JsonResponse({'code':RETCODE.OK, 'errmsg':'OK','cart_skus':cart_skus})

class OrderSettlementView(LoginRequiredMixin,View):
    """结算订单"""
    def get(self,request):
        #获取登录用户
        users = request.user
        return render(request, 'place_order.html')


class UserOrderInfoView(LoginRequiredMixin, View):
    def get(self, request, page_num):
        """提供我的订单页面"""
        user = request.user
        # 查询订单
        orders = user.orderinfo_set.all().order_by("-create_time")
        # 遍历所有订单
        for order in orders:
            # 绑定订单状态
            order.status_name = OrderInfo.ORDER_STATUS_CHOICES[order.status - 1][1]
            # 绑定支付方式
            order.pay_method_name = OrderInfo.PAY_METHOD_CHOICES[order.pay_method - 1][1]
            order.sku_list = []
            # 查询订单商品
            order_goods = order.skus.all()
            # 遍历订单商品
            for order_good in order_goods:
                sku = order_good.sku
                sku.count = order_good.count
                sku.amount = sku.price * sku.count
                order.sku_list.append(sku)

        # 分页
        page_num = int(page_num)
        try:
            paginator = Paginator(orders, constants.ORDERS_LIST_LIMIT)
            page_orders = paginator.page(page_num)
            total_page = paginator.num_pages
        except EmptyPage:
            return HttpResponseNotFound('订单不存在')

        context = {
            "page_orders": page_orders,
            'total_page': total_page,
            'page_num': page_num,
        }
        return render(request, "user_center_order.html", context)


class UserBrowseHistory(LoginRequiredJSONMixin, View):
    """用户浏览记录"""

    def post(self, request):
        """保存用户商品浏览记录"""
        # 接收参数
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        # 校验参数
        try:
            SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return HttpResponseForbidden('sku不存在')
        # 保存sku_id到redis
        redis_conn = get_redis_connection('history')
        pl = redis_conn.pipeline()
        user_id = request.user.id
        # 先去重
        pl.lrem('history_%s' % user_id, 0, sku_id)
        # 再存储
        pl.lpush('history_%s' % user_id, sku_id)
        # 最后截取
        pl.ltrim('history_%s' % user_id, 0, 4)
        # 执行管道
        pl.execute()
        # 响应结果
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})

    """用户浏览记录"""

    def get(self, request):
        """获取用户浏览记录"""
        # 获取Redis存储的sku_id列表信息
        redis_conn = get_redis_connection('history')
        sku_ids = redis_conn.lrange('history_%s' % request.user.id, 0, -1)
        # 根据sku_ids列表数据，查询出商品sku信息
        skus = []
        for sku_id in sku_ids:
            sku = SKU.objects.get(id=sku_id)
            skus.append({
                'id': sku.id,
                'name': sku.name,
                'default_image_url': settings.STATIC_URL + 'images/goods/' + sku.default_image.url + '.jpg',
                'price': sku.price
            })
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'skus': skus})


class ChangePasswordView(LoginRequiredMixin, View):
    """修改密码"""

    def get(self, request):
        """展示修改密码界面"""
        return render(request, 'user_center_pass.html')

    def post(self, request):
        """实现修改密码逻辑"""
        # 接收参数
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        new_password2 = request.POST.get('new_password2')
        # 校验参数
        if not all([old_password, new_password, new_password2]):
            return HttpResponseForbidden('缺少必传参数')
        try:
            if not request.user.check_password(old_password):
                return render(request, 'user_center_pass.html', {'origin_password_errmsg': '原始密码错误'})
        except Exception as e:
            logger.error(e)
            return render(request, 'user_center_pass.html', {'origin_password_errmsg': '查询密码失败'})
        if not re.match(r'^[0-9A-Za-z]{8,20}$', new_password):
            return HttpResponseForbidden('密码最少8位，最长20位')
        if new_password != new_password2:
            return HttpResponseForbidden('两次输入的密码不一致')
        # 修改密码
        try:
            request.user.set_password(new_password)
            request.user.save()
        except Exception as e:
            logger.error(e)
            return render(request, 'user_center_pass.html', {'change_pwd_errmsg': '修改密码失败'})
        # 清理状态保持信息
        logout(request)
        response = redirect(reverse('users:login'))
        response.delete_cookie('username')
        # 响应密码修改结果：重定向到登录界面
        return response


class UpdateTitleAddressView(LoginRequiredJSONMixin, View):
    """设置地址标题"""

    def put(self, request, address_id):
        """设置地址标题"""
        json_dict = json.loads(request.body.decode())  # 接收参数：地址标题
        title = json_dict.get('title')
        try:
            address = Address.objects.get(id=address_id)  # 查询地址
            address.title = title  # 设置新的地址标题
            address.save()
        except Exception as e:
            logger.error(e)
            return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '设置地址标题失败'})
        # 响应删除地址结果
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '设置地址标题成功'})


class DefaultAddressView(LoginRequiredJSONMixin, View):
    """设置默认地址"""

    def put(self, request, address_id):
        """设置默认地址"""
        try:
            address = Address.objects.get(id=address_id)  # 接收参数,查询地址
            request.user.default_address = address  # 设置地址为默认地址
            request.user.save()
        except Exception as e:
            logger.error(e)
            return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '设置默认地址失败'})
        # 响应设置默认地址结果
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '设置默认地址成功'})


class UpdateDestroyAddressView(LoginRequiredJSONMixin, View):
    def put(self, request, address_id):
        """修改地址"""
        json_dict = json.loads(request.body.decode())
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')
        # 校验参数
        if not all([receiver, province_id, city_id, district_id, place, mobile]):
            return HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return HttpResponseForbidden('参数email有误')
        # 判断地址是否存在,并更新地址信息
        try:
            Address.objects.filter(id=address_id).update(
                user=request.user, title=receiver, receiver=receiver,
                province_id=province_id, city_id=city_id, place=place,
                district_id=district_id, mobile=mobile, tel=tel,
                email=email
            )
        except Exception as e:
            logger.error(e)
            return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '更新地址失败'})
        # 构造响应数据
        address = Address.objects.get(id=address_id)
        address_dict = {
            "id": address.id, "title": address.title,
            "receiver": address.receiver, "province": address.province.name,
            "city": address.city.name, "district": address.district.name,
            "place": address.place, "mobile": address.mobile,
            "tel": address.tel, "email": address.email
        }
        # 响应更新地址结果
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '更新地址成功', 'address': address_dict})

    def delete(self, request, address_id):
        """删除地址"""
        default_address_id = request.user.default_address_id
        try:
            address = Address.objects.get(id=address_id)
            if default_address_id == address.id:
                request.user.default_address_id = None
                request.user.save()
            address.is_deleted = True
            address.save()
        except Exception as e:
            logger.error(e)
            return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '删除地址失败'})
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '删除地址成功'})


class AddressView(LoginRequiredMixin, View):
    """展示地址"""

    def get(self, request):
        """提供收货地址界面"""
        login_user = request.user  # 获取当前登录用户对象
        addresses = Address.objects.filter(user=login_user, is_deleted=False)
        address_list = []  # 将用户地址模型列表转字典列表
        for address in addresses:
            address_dict = {
                "id": address.id, "title": address.title,
                "receiver": address.receiver, "city": address.city.name,
                "province": address.province.name, "place": address.place,
                "district": address.district.name, "tel": address.tel,
                "mobile": address.mobile, "email": address.email
            }
            address_list.append(address_dict)
        context = {
            'default_address_id': login_user.default_address_id or '0',
            'addresses': address_list
        }
        return render(request, 'user_center_site.html', context)


class AddressCreateView(LoginRequiredJSONMixin, View):
    """新增地址"""

    def post(self, request):
        count = request.user.addresses.filter(is_deleted__exact=False).count()
        if count >= constants.USER_ADDRESS_COUNTS_LIMIT:
            return JsonResponse({"code": RETCODE.THROTTLINGERR, 'errmsg': "超出用户地址上限"})
        # 接收参数
        json_dict = json.loads(request.body.decode())
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')
        # 校验参数
        if not all([receiver, province_id, city_id, district_id, place, mobile]):
            return HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return HttpResponseForbidden('参数email有误')
        # 保存用户传入的地址信息
        try:
            address = Address.objects.create(
                user=request.user, title=receiver, receiver=receiver,
                province_id=province_id, place=place, tel=tel,
                city_id=city_id, district_id=district_id,
                mobile=mobile, email=email
            )
            # 设置默认地址
            if not request.user.default_address:
                request.user.default_address = address
                request.user.save()
        except Exception as e:
            logger.error(e)
            return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '新增地址失败'})
        # 新增地址成功，将新增的地址响应给前端实现局部刷新 构造新增地址字典数据
        address_dict = {
            "id": address.id, "title": address.title,
            "receiver": address.receiver, "province": address.province.name,
            "city": address.city.name, "district": address.district.name,
            "place": address.place, "mobile": address.mobile,
            "tel": address.tel, "email": address.email
        }
        # 响应新增地址结果：需要将新增的地址返回给前端渲染
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '新增地址成功', 'address': address_dict})


class VerifyEmailView(View):
    """验证邮箱"""

    def get(self, request):
        token = request.GET.get('token')  # 接收参数
        if not token:  # 校验参数
            return HttpResponseForbidden('缺少token')
        user = check_verify_email_token(token)  # 从token中提取用户信息
        if not user:
            return HttpResponseBadRequest('无效的token')
        try:
            user.email_active = True  # 将用户的email_active 设置为true
            user.save()
        except Exception as e:
            logger.error(e)
            return HttpResponseServerError('激活邮箱失败')
        # 响应结果：重定向到用户中心
        return redirect(reverse('users:info'))


class EmailView(LoginRequiredJSONMixin, View):
    """添加邮箱"""

    def put(self, request):
        """实现添加邮箱逻辑"""
        # 接收参数 body 类型是bytes类型
        json_str = request.body.decode()
        json_dict = json.loads(json_str)
        email = json_dict.get('email')
        if not email:  # 2.校验参数
            return HttpResponseForbidden('缺少email参数')
        if not re.match(r'^[a-z0-9][\w\\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return HttpResponseForbidden('参数email有误')
            # 赋值email字段
        try:
            request.user.email = email
            request.user.save()
        except Exception as e:
            logger.error(e)
            return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '添加邮箱失败'})
        # 异步发送验证邮件
        # verify_url = '邮件验证链接'
        verify_url = generate_verify_email_url(request.user)
        send_verify_email.delay(email, verify_url)

        # 响应添加邮箱结果
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '添加邮箱成功'})


class UserInfoView(LoginRequiredMixin, View):
    """用户中心"""

    def get(self, request):
        """提供用户中心页面"""
        context = {
            'username': request.user.username,
            'mobile': request.user.mobile,
            'email': request.user.email,
            'email_active': request.user.email_active
        }
        return render(request, 'user_center_info.html', context=context)


class LogoutView(View):
    """用户退出登录"""

    def get(self, request):
        # 清除状态保持信息
        logout(request)
        # 响应结果 重定向到首页
        response = redirect(reverse('contents:index'))
        # 删除cookie中的用户名
        response.delete_cookie('username')
        return response


class LoginView(View):
    """用户名登录"""

    def get(self, request):
        return render(request, 'login.html')

    def post(self, request):
        # 接收参数
        username = request.POST.get('username')
        password = request.POST.get('password')
        remembered = request.POST.get('remembered')
        # 校验参数
        if not all([username, password]):
            return HttpResponseForbidden('缺少必传参数')
        # 判断用户名是否是5-20个字符
        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return HttpResponseForbidden('请输入正确的用户名或手机号')
        # 判断密码是否是8-20个数字
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseForbidden('密码最少8位，最长20位')
        # 认证登录用户
        user = authenticate(username=username, password=password)
        if user is None:
            return render(request, 'login.html', {'account_errmsg': '账号或密码错误'})
        login(request, user)  # 实现状态保持
        if remembered != 'on':  # 设置状态保持的周期
            request.session.set_expiry(0)  # 没有记住用户：浏览器会话结束就过期
        else:
            request.session.set_expiry(None)  # 记住用户：None表示两周后过期
        # return redirect(reverse('contents:index')) # 响应登录结果
        # 响应登录结果
        # 先取出next
        next = request.GET.get('next')
        if next:
            # 重定向到next
            response = redirect(next)
        else:
            response = redirect(reverse('contents:index'))
        # 登录时用户名写入到cookie，有效期15天
        response.set_cookie('username', user.username, max_age=3600 * 24 * 15)
        response = merge_carts_cookies_redis(request=request, user=user, response=response)
        return response


class MoblieCountView(View):
    def get(self, request, mobile):
        """
        :param mobile: 手机号码
        :return:json
        """
        # 接收输入的手机号码
        count = User.objects.filter(mobile=mobile).count()
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', "count": count})


class UsernameCountView(View):
    """判断用户名是否重复注册"""

    def get(self, request, username):
        """
        :param request: 请求对象
        :param username: 用户名
        :return: JSON
        """
        count = User.objects.filter(username=username).count()
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'count': count})


class RegisterView(View):
    """用户注册"""

    def get(self, request):
        """提供用户注册页面"""
        return render(request, 'register.html')

    def post(self, request):
        """实现用户注册业务逻辑"""
        username = request.POST.get("username")  # 用户名
        password = request.POST.get("password")  # 密码
        password2 = request.POST.get("password2")  # 确认密码
        mobile = request.POST.get("mobile")  # 手机号
        sms_code_client = request.POST.get('sms_code')  # 短信验证码
        allow = request.POST.get("allow")  # 是否同意协议
        if not all([username, password, password2, mobile, sms_code_client, allow]):
            # if not all([username, password, password2, mobile, allow]):
            # 返回403  禁止请求
            return HttpResponseForbidden("缺少必传参数")
        # 判断用户名是否是5-20个字符
        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return HttpResponseForbidden("请输入5-20个字符的用户名")
        # 判断密码是否是8-20个字符
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseForbidden("请输入8-20位的密码")
        # 判断两次输入的密码是否相同
        if password != password2:
            return HttpResponseForbidden("两次输入的密码不一致")
        # 判断手机号码是否合法
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseForbidden("您输入的手机号格式不正确")

        # 判断短信验证码是否输入正确
        redis_conn = get_redis_connection("verify_code")
        sms_code_server = redis_conn.get('sms_%s' % mobile)
        if sms_code_server is None:
            return render(request, 'register.html', {"sms_code_errmsg": "短信验证码已失效"})
        if sms_code_client != sms_code_server.decode():
            return render(request, 'register.html', {"sms_code_errmsg": "输入短信验证码有误"})

        # 判断用户是否勾选协议
        if allow != 'on':
            return HttpResponseForbidden("请勾选用户协议")
        # 保存注册数据：是注册业务的核心
        try:
            #  注册成功的用户对象
            user = User.objects.create_user(username=username, mobile=mobile, password=password, )
        except DatabaseError:
            return render(request, 'register.html', {'register_errmsg': '注册失败'})
        login(request, user)  # 登入用户，实现状态保持
        # 响应登录结果:重定向到首页
        response = redirect(reverse('contents:index'))
        # 为了实现在首页右上角展示用户信息，我们需要将用户名缓存到cookie中
        response.set_cookie('username', user.username, max_age=3600 * 24 * 14)
        return response
