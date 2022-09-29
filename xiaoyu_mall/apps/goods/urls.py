from django.urls import path
from . import views

# 设置应用程序命名空间
app_name = 'goods'
urlpatterns = [
    # 商品列表页
    path('list/<int:category_id>/<int:page_num>/', views.ListView.as_view(), name='list'),
    # 热销排行
    path('hot/<int:category_id>/', views.HostGoodsView.as_view()),
    # 商品详情
    path('detail/<int:sku_id>/', views.DetailView.as_view(), name='detail'),
    # 统计商品分类的访问量
    path('detail/visit/<int:category_id>/', views.DetailVisitView.as_view()),
    # 商品评价
    path('comments/<int:sku_id>/', views.GoodsCommentView.as_view()),

]
