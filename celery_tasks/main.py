# celery_tasks/main.py
# celery的入口
from celery import Celery
# 为celery使用django配置文件进行设置
import os
if not os.getenv('DJANGO_SETTINGS_MODULE'):
    os.environ['DJANGO_SETTINGS_MODULE'] = 'xiaoyu_mall.settings.dev'
# 创建celery实例
celery_app = Celery('xioayu')
# 加载配置 指定中间人
celery_app.config_from_object('celery_tasks.config')
# 注册任务
celery_app.autodiscover_tasks(['celery_tasks.email'])