from django.contrib import admin
from .models import VpsServer, Provedor, Company

@admin.register(VpsServer)
class VpsServerAdmin(admin.ModelAdmin):
    list_display = ('name', 'api_url', 'max_capacity', 'is_active')
    search_fields = ('name', 'api_url')
    list_filter = ('is_active',)

@admin.register(Provedor)
class ProvedorAdmin(admin.ModelAdmin):
    list_display = ('nome', 'vps', 'subdomain', 'is_active')
    search_fields = ('nome', 'subdomain')
    list_filter = ('is_active', 'vps')

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active')
    search_fields = ('name', 'slug')
