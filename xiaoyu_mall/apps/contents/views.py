from django.shortcuts import render
from django.views import View

from contents.utils import get_categories
from collections import OrderedDict
from contents.models import ContentCategory


class IndexView(View):
    def get(self, request):
        """提供首页广告页面"""
        categories = get_categories()
        # 查询首页广告数据
        # 查询所有的广告类别
        content_categories = ContentCategory.objects.all()
        # 使用广告类别查询出该类别对应的所有的广告内容
        contents = OrderedDict()
        for content_categorie in content_categories:
            contents[content_categorie.key] = content_categorie.content_set.filter(status=True).order_by('sequence')  # 查询出未下架的广告并排序
        # 渲染模板的上下文
        context = {
                'categories': categories,
                'contents': contents,
            }
        return render(request, 'index.html', context)
