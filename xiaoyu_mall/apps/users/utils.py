from django.contrib.auth.backends import ModelBackend
from users.models import User
import re
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import BadData
from django.conf import settings
from . import constants


def check_verify_email_token(token):
    """
    反序列token，获取user
    :param token: 序列化后的用户信息
    :return:user
    """
    serializer = Serializer(settings.SECRET_KEY, expires_in=constants.VERIFY_EMAIL_TOKEN_EXPIRES)
    try:
        data = serializer.loads(token)
    except BadData:
        return None
    else:
        # 从data取出user_id和email
        user_id = data.get('user_id')
        email = data.get('email')
        try:
            user = User.objects.get(id=user_id, email=email)
        except User.DoesNotExist:
            return None
        else:
            return user


def generate_verify_email_url(user):
    serializer = Serializer(settings.SECRET_KEY, expires_in=constants.VERIFY_EMAIL_TOKEN_EXPIRES)
    data = {'user_id': user.id, 'email': user.email}
    token = serializer.dumps(data).decode()
    verify_url = settings.EMAIL_VERIFY_URL + '?token=' + token
    return verify_url


def get_user_by_account(account):
    try:
        if re.match(r'^1[3-9]\d{9}', account):
            user = User.objects.get(mobile=account)
        else:
            user = User.objects.get(username=account)
    except User.DoesNotExist:
        return None
    else:
        return user


class UsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        重写用户认证方法
        :param username: 用户名或手机号
        :param password: 密码明文
        :param kwargs: 额外参数
        :return:user
        """
        user = get_user_by_account(username)
        if user and user.check_password(password):
            return user
        else:
            return None
