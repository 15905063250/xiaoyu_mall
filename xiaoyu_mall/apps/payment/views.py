from django.shortcuts import render
import os
from django.views import View
from orders.models import OrderInfo
from alipay import AliPay
from xiaoyu_mall.utils.views import LoginRequiredJSONMixin
from xiaoyu_mall.utils.response_code import RETCODE
from django.http import HttpResponseForbidden, JsonResponse
from django.conf import settings
from .models import Payment
import json
from xiaoyu_mall.utils.views import LoginRequiredMixin
from orders.models import OrderInfo, OrderGoods
from django.http import HttpResponseNotFound, HttpResponseServerError
from goods.models import SKU


# Create your views here.
class OrderCommentView(LoginRequiredMixin, View):
    """订单商品评价"""

    def get(self, request):
        """展示商品评价页面"""
        # 接收参数
        order_id = request.GET.get('order_id')
        # 校验参数
        try:
            OrderInfo.objects.get(order_id=order_id, user=request.user)
        except OrderInfo.DoesNotExist:
            return HttpResponseNotFound('订单不存在')

        # 查询订单中未被评价的商品信息
        try:
            uncomment_goods = OrderGoods.objects.filter(order_id=order_id, is_commented=False)
        except Exception:
            return HttpResponseServerError('订单商品信息出错')

        # 构造待评价商品数据
        uncomment_goods_list = []
        for goods in uncomment_goods:
            uncomment_goods_list.append({
                # 订单号
                'order_id': goods.order.order_id,
                # 商品sku_id
                'sku_id': goods.sku.id,
                # 商品名称
                'name': goods.sku.name,
                # 商品价格
                'price': str(goods.price),
                # 商品图片
                'default_image_url': settings.STATIC_URL + 'images/goods/' + goods.sku.default_image.url + '.jpg',
                # 商品评价内容
                'comment': goods.comment,
                # 商品评分
                'score': goods.score,
                # 匿名用户
                'is_anonymous': str(goods.is_anonymous),
            })

        # 渲染模板
        context = {
            'uncomment_goods_list': uncomment_goods_list
        }
        return render(request, 'goods_judge.html', context)

    def post(self, request):
        """评价订单商品"""
        # 接收参数
        json_dict = json.loads(request.body.decode())
        order_id = json_dict.get('order_id')
        sku_id = json_dict.get('sku_id')
        score = json_dict.get('score')
        comment = json_dict.get('comment')
        is_anonymous = json_dict.get('is_anonymous')
        # 校验参数
        if not all([order_id, sku_id, score, comment]):
            return HttpResponseForbidden('缺少必传参数')
        try:
            OrderInfo.objects.filter(order_id=order_id, user=request.user,
                                     status=OrderInfo.ORDER_STATUS_ENUM['UNCOMMENT'])
        except OrderInfo.DoesNotExist:
            return HttpResponseForbidden('参数order_id错误')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return HttpResponseForbidden('参数sku_id错误')
        if is_anonymous:
            if not isinstance(is_anonymous, bool):
                return HttpResponseForbidden('参数is_anonymous错误')

        # 保存订单商品评价数据
        OrderGoods.objects.filter(order_id=order_id, sku_id=sku_id, is_commented=False).update(
            comment=comment,
            score=score,
            is_anonymous=is_anonymous,
            is_commented=True
        )

        # 累计评论数据
        sku.comments += 1
        sku.save()
        sku.spu.comments += 1
        sku.spu.save()

        # 如果所有订单商品都已评价，则修改订单状态为已完成
        if OrderGoods.objects.filter(order_id=order_id, is_commented=False).count() == 0:
            OrderInfo.objects.filter(order_id=order_id).update(status=OrderInfo.ORDER_STATUS_ENUM['FINISHED'])

        return JsonResponse({'code': RETCODE.OK, 'errmsg': '评价成功'})


class PaymentStatusView(View):
    """保存订单支付结果"""

    def get(self, request):
        query_dict = request.GET  # 获取前端传入的请求参数
        data = query_dict.dict()
        signature = data.pop('sign')  # 从请求参数中剔除signature

        # 创建支付宝支付对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,
            app_private_key_string=open(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys/app_private_key.pem")).read(),
            alipay_public_key_string=open(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys/alipay_public_key.pem")).read(),
            sign_type="RSA2",
            debug=settings.ALIPAY_DEBUG
        )
        # 校验这个重定向是否是alipay重定向过来的
        success = alipay.verify(data, signature)
        if success:
            order_id = data.get('out_trade_no')  # 读取order_id
            trade_id = data.get('trade_no')  # 读取支付宝流水号
            # 保存Payment模型类数据
            Payment.objects.create(
                order_id=order_id,
                trade_id=trade_id
            )
            # 修改订单状态为待评价
            OrderInfo.objects.filter(order_id=order_id, status=OrderInfo.ORDER_STATUS_ENUM['UNPAID']).update(
                status=OrderInfo.ORDER_STATUS_ENUM["UNCOMMENT"])
            # 响应trade_id
            context = {
                'trade_id': trade_id
            }

            return render(request, 'pay_success.html', context)
        else:
            # 订单支付失败，重定向到我的订单
            return HttpResponseForbidden('非法请求')


class PaymentView(LoginRequiredJSONMixin, View):
    """订单支付功能"""

    def get(self, request, order_id):
        # 查询要支付的订单
        user = request.user
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user, status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'])
        except OrderInfo.DoesNotExist:
            return HttpResponseForbidden('订单信息错误')
        # 创建支付宝支付对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调url
            app_private_key_string=open(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys/app_private_key.pem")).read(),
            alipay_public_key_string=open(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys/alipay_public_key.pem")).read(),

            sign_type="RSA2",
            debug=settings.ALIPAY_DEBUG
        )
        # SDK对象对接支付宝支付的接口，得到登录页的地址
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 订单编号
            total_amount=str(order.total_amount),  # 订单金额
            subject="小鱼商城%s" % order_id,  # 订单标题
            return_url=settings.ALIPAY_RETURN_URL  # 回调地址
        )
        # 响应登录支付宝连接
        alipay_url = settings.ALIPAY_URL + "?" + order_string
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'alipay_url': alipay_url})
