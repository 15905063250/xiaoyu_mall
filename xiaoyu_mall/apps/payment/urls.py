from django.urls import re_path, path
from . import views
app_name = 'payment'
urlpatterns = [
    # 支付
    re_path('payment/(?P<order_id>\d+)/',views.PaymentView.as_view()),
    # 保存订单
    path('payment/status/',views.PaymentStatusView.as_view()),
    # 评价
    path('orders/comment/', views.OrderCommentView.as_view()),
]
