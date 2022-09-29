from django.urls import path
from . import views
app_name = 'carts'
urlpatterns = [
    # 购物车管理
    path('carts/', views.CartsView.as_view(), name='info'),
    # 选择购物车商品
    path('carts/selection/', views.CartsSelectAllView.as_view()),
    # 简单购物车
    path('carts/simple/', views.CartsSimpleView.as_view()),
    #购物车略缩信息
    path('carts/simple/',views.CartsSimpleView.as_view()),
    #订单结算
    # path('', include('orders.urls', namespace='orders')),
]
