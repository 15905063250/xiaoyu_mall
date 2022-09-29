from django.conf import settings
from django.core.paginator import Paginator, EmptyPage
from django.shortcuts import render
from django.views import View
from datetime import datetime
from goods.utils import get_breadcrumb
from xiaoyu_mall.utils.response_code import RETCODE
from .models import GoodsCategory, SKU
from contents.utils import get_categories
from django.http import HttpResponseForbidden, HttpResponseNotFound, JsonResponse, HttpResponseServerError
from django.utils import timezone  # 处理时间
from orders.models import OrderGoods
from goods.models import SKU, GoodsVisitCount
import logging
logger = logging.error('django')
# Create your views here.
class GoodsCommentView(View):
    """订单商品评价信息"""

    def get(self, request, sku_id):
        # 获取被评价的订单商品信息
        order_goods_list = OrderGoods.objects.filter(sku_id=sku_id, is_commented=True).order_by('-create_time')[:30]
        # 序列化
        comment_list = []
        for order_goods in order_goods_list:
            username = order_goods.order.user.username
            comment_list.append({
                'username': username[0] + '***' + username[-1]
                if order_goods.is_anonymous else username,
                'comment': order_goods.comment,
                'score': order_goods.score,
            })
            # print('评价信息')
            # print(comment_list)
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'comment_list': comment_list})


class DetailVisitView(View):
    """统计分类商品访问量"""

    def post(self, request, category_id):
        """记录分类商品访问量"""
        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return HttpResponseForbidden('缺少必传参数')

        # 获取今天的日期
        t = timezone.localtime()
        today_str = '%d-%02d-%02d' % (t.year, t.month, t.day)
        today_date = datetime.strptime(today_str, '%Y-%m-%d')
        try:
            # 查询今天该类别的商品的访问量
            counts_data = category.goodsvisitcount_set.get(date=today_date)
        except GoodsVisitCount.DoesNotExist:
            # 如果该类别的商品在今天没有过访问记录，就新建一个访问记录
            counts_data = GoodsVisitCount()

        try:
            counts_data.category = category
            counts_data.count += 1
            counts_data.save()
        except Exception as e:
            logger.error(e)
            return HttpResponseServerError('服务器异常')

        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class DetailView(View):
    """商品详情页"""

    def get(self, request, sku_id):
        """提供商品详情页"""
        # 获取当前sku的信息
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return render(request, '404.html')

        # 查询商品频道分类
        categories = get_categories()
        # 查询面包屑导航
        breadcrumb = get_breadcrumb(sku.category)

        # 构建当前商品的规格键
        sku_specs = sku.specs.order_by('spec_id')
        sku_key = []
        for spec in sku_specs:
            sku_key.append(spec.option.id)
        # 获取当前商品的所有SKU
        skus = sku.spu.sku_set.all()
        # 构建不同规格参数（选项）的sku字典
        spec_sku_map = {}
        for s in skus:
            # 获取sku的规格参数
            s_specs = s.specs.order_by('spec_id')
            # 用于形成规格参数-sku字典的键
            key = []
            for spec in s_specs:
                key.append(spec.option.id)
            # 向规格参数-sku字典添加记录
            spec_sku_map[tuple(key)] = s.id
        # 获取当前商品的规格信息
        goods_specs = sku.spu.specs.order_by('id')
        # 若当前sku的规格信息不完整，则不再继续
        if len(sku_key) < len(goods_specs):
            return
        for index, spec in enumerate(goods_specs):
            # 复制当前sku的规格键
            key = sku_key[:]
            # 该规格的选项
            spec_options = spec.options.all()
            for option in spec_options:
                # 在规格参数sku字典中查找符合当前规格的sku
                key[index] = option.id
                option.sku_id = spec_sku_map.get(tuple(key))
            spec.spec_options = spec_options

        # 渲染页面
        context = {
            'categories': categories,
            'breadcrumb': breadcrumb,
            'sku': sku,
            'specs': goods_specs,

            # 商品数量
            'stock': sku.stock
        }
        return render(request, 'detail.html', context)


class ListView(View):
    """商品列表页"""

    def get(self, request, category_id, page_num):
        """查询并渲染商品列表页"""
        # 校验参数
        try:
            # 三级类别
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return HttpResponseForbidden("参数category_id不存在")
        # 获取sort（排序规则）  如果sort没有值，取default
        sort = request.GET.get('sort', 'default')
        # 根据sort选择排排序字段, 排序字段必须是模型类的属性
        if sort == 'price':  # 按照价格由低到高排序
            sort_field = 'price'
        elif sort == 'hot':
            sort_field = '-sales'  # 按照销量由高到低排序
        else:  # 只要不是price和-sales其他的所有情况都归为default
            sort = 'default'
            sort_field = 'create_time'
        # 查询商品分类
        categories = get_categories()
        # 查询面包屑导航：一级 ==>二级==>一级
        breadcrumb = get_breadcrumb(category)

        # 分页和排序查询 category查询sku 一查多
        skus = category.sku_set.filter(is_launched=True).order_by(sort_field)
        # 创建分页器
        # Paginator('要分页的记录','每页记录的条数')
        paginator = Paginator(skus, 5)  # 把skus进行分页，每页5条记录
        # 需要获取用户当前要看的那一页
        try:
            page_skus = paginator.page(page_num)  # 获取到page_num页中的5条记录
        except EmptyPage:
            return HttpResponseNotFound('Empty Page')
        # 获取总页数: 前端的分页插件需要使用
        total_page = paginator.num_pages
        # 构造上下文
        context = {
            'categories': categories,
            'breadcrumb': breadcrumb,
            'page_skus': page_skus,
            'total_page': total_page,
            'page_num': page_num,
            'sort': sort,
            'category_id': category_id,
        }
        return render(request, 'list.html', context)


class HostGoodsView(View):
    """热销排行"""

    def get(self, request, category_id):
        # 要查询指定分类的sku信息，而且必须是一个上架转态，然后按照由高到低排序，最后切片取出前两位
        skus = SKU.objects.filter(category_id=category_id, is_launched=True).order_by('-sales')[:2]
        # 将模型列表转字典构造json数据
        hot_skus = []

        for sku in skus:
            sku_dict = {
                'id': sku.id,
                'name': sku.name,
                'price': sku.price,
                'default_image_url': settings.STATIC_URL + 'images/goods/' + sku.default_image.url + '.jpg'
            }
            hot_skus.append(sku_dict)
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'hot_skus': hot_skus})
