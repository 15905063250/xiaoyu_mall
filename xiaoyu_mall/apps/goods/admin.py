from django.contrib import admin
from .models import SKU
@admin.register(SKU)
class GoodsAdmin(admin.ModelAdmin):
    # 显示列表
    list_display = ['id', 'name', 'create_time', 'update_time', 'price',
                    'cost_price', 'market_price', 'stock', 'sales','comments']
