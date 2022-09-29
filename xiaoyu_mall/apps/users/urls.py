from django.urls import path, re_path
from . import views

# 设置应用程序命名空间
app_name = 'users'
urlpatterns = [
    # 用户注册
    path('register/', views.RegisterView.as_view(), name='register'),
    # 用户名是否重复
    re_path('usernames/(?P<username>[a-zA-Z0-9_-]{5,20})/count/', views.UsernameCountView.as_view()),
    # 手机号重复注册
    re_path(r'mobiles/(?P<mobile>1[3-9]\d{9})/count/', views.MoblieCountView.as_view()),
    # 登录
    path('login/', views.LoginView.as_view(), name='login'),
    # 退出
    path('logout/', views.LogoutView.as_view(), name='logout'),  # 用户退出
    # 用户中心
    path('info/', views.UserInfoView.as_view(), name='info'),
    # 添加邮箱
    path('emails/', views.EmailView.as_view()),
    # 验证邮箱
    path('emails/verification/', views.VerifyEmailView.as_view()),
    # 新增用户地址
    path('addresses/create/', views.AddressCreateView.as_view()),
    # 展示地址
    path('addresses/', views.AddressView.as_view(), name='address'),
    # 修改与删除地址
    path('addresses/<int:address_id>/', views.UpdateDestroyAddressView.as_view()),
    # 设置默认地址
    path('addresses/<int:address_id>/default/', views.DefaultAddressView.as_view()),
    # 设置标题
    path('addresses/<int:address_id>/title/', views.UpdateTitleAddressView.as_view()),
    # 修改密码
    path('editpassword/', views.ChangePasswordView.as_view(), name='pass'),
    # 浏览记录
    path('browse_histories/', views.UserBrowseHistory.as_view()),
    # 全部订单
    path('orders/info/<int:page_num>/', views.UserOrderInfoView.as_view(), name='myorderinfo'),
]
