from django.contrib.auth.mixins import LoginRequiredMixin
from xiaoyu_mall.utils.response_code import RETCODE
from django.http import JsonResponse
class LoginRequiredJSONMixin(LoginRequiredMixin):
    """自定义判断用户是否登录的扩展类：返回JSON"""
    def handle_no_permission(self):
        return JsonResponse({'code': RETCODE.SESSIONERR, 'errmsg': '用户未登录'})
