from django.apps import AppConfig
import os
# 修改app在Admin后台显示
default_app_config = 'goods.IndexConfig'
# 获取当前应用名称
def get_current_app_name(_file):
    return os.path.split(os.path.dirname((_file)))[-1]
# 重写IndexConfig
class IndexConfig(AppConfig):
    name = get_current_app_name(__file__)
    verbose_name = "商品SKU"
