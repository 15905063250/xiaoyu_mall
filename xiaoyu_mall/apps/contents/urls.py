from django.urls import path,re_path
from . import views
# 设置应用程序命名空间
app_name = 'contents'
urlpatterns = [
    # 首页
    path("", views.IndexView.as_view(), name='index')
]
