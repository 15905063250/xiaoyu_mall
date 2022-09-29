from django.urls import path,re_path
from . import views
urlpatterns = [
    # 图形验证码
    path('image_codes/<uuid:uuid>/', views.ImageCodeView.as_view()),
    # 短信验证码
    re_path('sms_codes/(?P<mobile>1[3-9]\d{9})/',views.SMSCodeView.as_view())
]
