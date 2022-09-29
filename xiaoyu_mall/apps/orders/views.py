from django.shortcuts import render
from django.views import View
from xiaoyu_mall.utils.views import LoginRequiredMixin
import logging

logger = logging.getLogger('django')
from users.models import Address
from django_redis import get_redis_connection
from goods.models import SKU
from decimal import Decimal
import json
from xiaoyu_mall.utils.views import LoginRequiredJSONMixin
from django.http import HttpResponseForbidden
from .models import OrderInfo, OrderGoods
from django.utils import timezone
from django.http import JsonResponse
from xiaoyu_mall.utils.response_code import RETCODE
from django.db import transaction


class OrderSuccessView(LoginRequiredMixin, View):
    """提交订单成功页面"""

    def get(self, request):
        """提供提交订单成功页面"""
        order_id = request.GET.get('order_id')
        payment_amount = request.GET.get('payment_amount')
        pay_method = request.GET.get('pay_method')
        context = {
            'order_id': order_id,
            'payment_amount': payment_amount,
            'pay_method': pay_method
        }
        return render(request, 'order_success.html', context)


class OrderCommitView(LoginRequiredJSONMixin, View):
    """提交订单"""

    def post(self, request):
        """保存订单基本信息和订单商品信息"""
        # 接收参数
        json_dict = json.loads(request.body.decode())
        address_id = json_dict.get('address_id')
        pay_method = json_dict.get('pay_method')
        # 校验参数
        if not all([address_id, pay_method]):
            return HttpResponseForbidden('缺少必传参数')
            # 判断address_id是否合法
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return HttpResponseForbidden('参数address_id错误')
        # 判断pay_method是否合法
        if pay_method not in [OrderInfo.PAY_METHODS_ENUM['CASH'], OrderInfo.PAY_METHODS_ENUM['ALIPAY']]:
            return HttpResponseForbidden('参数pay_method错误')
        # 获取登录用户
        user = request.user
        # 获取订单编号：时间+user_id
        order_id = timezone.localtime().strftime('%Y%m%d%H%M%S') + ('%09d' % user.id)
        # 显示开启一个事务
        with transaction.atomic():
            # 创建事务保存点
            save_id = transaction.savepoint()
            # 回滚
            try:
                # 保存订单基本信息（一）
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address=address,
                    total_count=0,
                    total_amount=Decimal(0.00),
                    freight=Decimal(10.00),
                    pay_method=pay_method,
                    status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'] if pay_method == OrderInfo.PAY_METHODS_ENUM[
                        'ALIPAY'] else OrderInfo.ORDER_STATUS_ENUM['UNSEND']
                )
                # 从redis读取购物⻋中被勾选的商品信息
                redis_conn = get_redis_connection('carts')
                redis_cart = redis_conn.hgetall('carts_%s' % user.id)
                selected = redis_conn.smembers('selected_%s' % user.id)
                carts = {}
                for sku_id in selected:
                    carts[int(sku_id)] = int(redis_cart[sku_id])
                sku_ids = carts.keys()
                # 遍历购物车中被勾选的商品信息
                for sku_id in sku_ids:
                    while True:
                        # 查询SKU信息
                        sku = SKU.objects.get(id=sku_id)
                        # 读取原始库存
                        origin_stock = sku.stock
                        origin_sales = sku.sales
                        # 判断SKU库存
                        sku_count = carts[sku.id]
                        if sku_count > sku.stock:
                            # 事务回滚
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'code': RETCODE.STOCKERR, 'errmsg': '库存不足'})
                        # # SKU减少库存，增加销量
                        # sku.stock -= sku_count
                        # sku.sales += sku_count
                        # sku.save()
                        new_stock = origin_stock - sku_count
                        new_sales = origin_sales + sku_count
                        # 基于乐观锁的数据更新
                        result = SKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock,
                                                                                          sales=new_sales)
                        # 如果下单失败，但库存充足，继续下单，直到下单成功或库存不足
                        if result == 0:
                            continue

                        # 修改SPU销量
                        sku.spu.sales += sku_count
                        sku.spu.save()
                        # 保存订单商品信息 OrderGoods（多）
                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=sku_count,
                            price=sku.price,
                        )
                        # 保存商品订单中总价和总数量
                        order.total_count += sku_count
                        order.total_amount += (sku_count * sku.price)
                        # 下单成功，跳出循环
                        break
                # 添加邮费和保存订单信息
                order.total_amount += order.freight
                order.save()
            except Exception as e:
                logger.error(e)
                transaction.savepoint_rollback(save_id)  # 出错回滚
                return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '下单失败'})
        # 清除购物车中已结算的商品
        pl = redis_conn.pipeline()
        pl.hdel('carts_%s' % user.id, *selected)
        pl.srem('selected_%s' % user.id, *selected)
        pl.execute()
        # 响应提交订单结果
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '下单成功', 'order_id': order.order_id})


class OrderSettlementView(LoginRequiredMixin, View):
    """结算订单"""

    def get(self, request):
        # 获取登录用户
        user = request.user
        # 查询地址信息
        try:
            addresses = Address.objects.filter(user=user, is_deleted=False)
            # 如果没有查询出地址，去编辑收货地址
            if len(addresses) == 0:
                address_list = []

                # 构造上下文
                context = {
                    'addresses': address_list  # 使用空列表替代空的addresses
                }
                return render(request, 'user_center_site.html', context)
        except Exception as e:
            # 处理异常
            logger(e)

        # 查询redis购物车中被勾选的商品
        redis_conn = get_redis_connection('carts')
        # 所有的购物车数据，包含了勾选和未勾选 ：{b'1': b'1', b'2': b'2'}
        redis_cart = redis_conn.hgetall('carts_%s' % user.id)
        # 被勾选的商品的sku_id：[b'1']
        redis_selected = redis_conn.smembers('selected_%s' % user.id)
        # 构造购物车中被勾选的商品的数据 {b'1': b'1'}
        new_cart_dict = {}
        for sku_id in redis_selected:
            new_cart_dict[int(sku_id)] = int(redis_cart[sku_id])
        # 获取被勾选的商品的sku_id
        sku_ids = new_cart_dict.keys()
        skus = SKU.objects.filter(id__in=sku_ids)
        total_count = 0
        total_amount = Decimal(0.00)
        # 取出所有的sku
        for sku in skus:
            # 遍历skus给每个sku补充count（数量）和amount（小计）
            sku.count = new_cart_dict[sku.id]
            sku.amount = sku.price * sku.count  # Decimal类型的
            # 累加数量和金额
            total_count += sku.count
            total_amount += sku.amount  # 类型不同不能运算
        freight = Decimal(10.00)
        context = {
            'addresses': addresses,  # 收货地址
            'skus': skus,  # 商品
            'total_count': total_count,  # 商品总数量
            'total_amount': total_amount,  # 商品总金额
            'freight': freight,  # 运费
            'payment_amount': total_amount + freight,  # 实付款
        }

        return render(request, 'place_order.html', context)
