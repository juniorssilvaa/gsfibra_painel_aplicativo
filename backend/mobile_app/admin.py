from django.contrib import admin

from . import models


@admin.register(models.MobileAppProfile)
class MobileAppProfileAdmin(admin.ModelAdmin):
    list_display = ('provedor', 'is_active', 'cnpj', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('provedor__nome', 'cnpj', 'number')
    raw_id_fields = ('provedor',)


@admin.register(models.MobileAppUser)
class MobileAppUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'cpf', 'provedor', 'active', 'last_active_at', 'created_at')
    list_filter = ('active', 'provedor')
    search_fields = ('name', 'cpf', 'email', 'customer_id')
    raw_id_fields = ('provedor',)


@admin.register(models.MobileDevice)
class MobileDeviceAdmin(admin.ModelAdmin):
    list_display = ('platform', 'model', 'provedor', 'active', 'last_active', 'push_confirmed')
    list_filter = ('platform', 'active', 'provedor')
    raw_id_fields = ('user', 'provedor')


admin.site.register(models.MobileAppConfig)
admin.site.register(models.MobileProviderToken)
admin.site.register(models.MobileInAppWarning)
admin.site.register(models.MobilePlan)
admin.site.register(models.MobileSystemSettings)
