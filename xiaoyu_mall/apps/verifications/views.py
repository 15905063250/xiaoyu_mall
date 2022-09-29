from django.views import View
from .libs.captcha.captcha import captcha
from django_redis import get_redis_connection
from . import constants
from django.http import HttpResponse, JsonResponse
from verifications.libs.yuntongxun.ccp_sms import CCP
from django.http import JsonResponse
from xiaoyu_mall.utils.response_code import RETCODE
import random

import logging
# 日志记录器
logger = logging.getLogger('django')

class SMSCodeView(View):
    """短信验证码"""
    def get(self, reqeust, mobile):
        """
        :param reqeust: 请求对象
        :param mobile: 手机号
        :return: JSON
        """
        # 接收参数
        image_code_client = reqeust.GET.get('image_code')
        uuid = reqeust.GET.get('uuid')
        # 校验参数
        if not all([image_code_client, uuid]):
            return JsonResponse({'code': RETCODE.NECESSARYPARAMERR, 'errmsg': '缺少必传参数'})
        # 创建连接到redis的对象
        redis_conn = get_redis_connection('verify_code')
        # 提取图形验证码
        image_code_server = redis_conn.get('img_%s' % uuid)
        if image_code_server is None:
            # 图形验证码过期或者不存在
            return JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '图形验证码失效'})
        # 删除图形验证码，避免恶意测试图形验证码
        redis_conn.delete('img_%s' % uuid)
        # 对比图形验证码
        image_code_server = image_code_server.decode()  # bytes转字符串
        if image_code_client.lower() != image_code_server.lower():
            return JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '输入图形验证码有误'})
        # 生成短信验证码：生成6位数验证码
        sms_code = '%06d' % random.randint(0, 999999)
        logger.info(sms_code)
        # 保存短信验证码
        redis_conn.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        # 发送短信验证码
        print(sms_code)
        CCP().send_template_sms(mobile,[sms_code, constants.SMS_CODE_REDIS_EXPIRES // 60], constants.SEND_SMS_TEMPLATE_ID)
        # # 创建redis管道
        # pl = redis_conn.pipeline()
        # #  将命令添加到队列中
        # # 保存短信验证码
        # pl.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        # # 保存发送短信验证码的标记
        # pl.setex('send_flag_%s' % mobile, constants.SEND_SMS_CODE_INTERVAL, 1)
        # # # 执行
        # pl.execute()
        # # 发送短信验证码
        # CCP().send_template_sms(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRES // 60],
        #                         constants.SEND_SMS_TEMPLATE_ID)
        # 响应结果
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '发送短信成功'})


class ImageCodeView(View):
    def get(self, request, uuid):
        """
        :param uuid:通用唯一识别码，用于唯一标识该图形验证码属于哪一个用户的
        :return:image/jpg
        """
        # 生成图形验证码
        text, image = captcha.generate_captcha()
        # 保存图形验证码
        redis_conn = get_redis_connection('verify_code')
        # setex 保存到redis中 并设置生存时间
        redis_conn.setex('img_%s' % uuid, constants.IMAGE_CODE_REDIS_EXPIRES, text)
        # 响应图形验证码
        return HttpResponse(image, content_type='image/jpg')
