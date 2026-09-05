from django.contrib import admin

from . import models


@admin.register(models.AcsProfile)
class AcsProfileAdmin(admin.ModelAdmin):
    list_display = ('provedor', 'is_active', 'update_channel', 'current_version', 'last_check')
    list_filter = ('is_active', 'update_channel')
    search_fields = ('provedor__nome',)
    raw_id_fields = ('provedor',)


@admin.register(models.AcsLicense)
class AcsLicenseAdmin(admin.ModelAdmin):
    list_display = ('key', 'profile', 'status', 'expiration_date', 'max_onts')
    list_filter = ('status',)
    search_fields = ('key', 'profile__provedor__nome')
    raw_id_fields = ('profile',)


@admin.register(models.AcsHardwareBind)
class AcsHardwareBindAdmin(admin.ModelAdmin):
    list_display = ('machine_name', 'profile', 'last_ip', 'last_seen', 'status')
    list_filter = ('status',)
    search_fields = ('machine_name', 'hwid_hash')
    raw_id_fields = ('profile', 'license')


admin.site.register(models.AcsRelease)
admin.site.register(models.AcsDeploymentLog)
