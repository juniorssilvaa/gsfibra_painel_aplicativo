from rest_framework import serializers
from .models import TelegramIntegration, EmailIntegration, WhatsAppIntegration, WebchatIntegration


# ============================================================
#   TELEGRAM SERIALIZER COMPLETO (COM TELEGRAM INFO)
# ============================================================

class TelegramIntegrationSerializer(serializers.ModelSerializer):
    telegramInfo = serializers.SerializerMethodField()
    session_string = serializers.CharField(read_only=True)

    class Meta:
        model = TelegramIntegration
        fields = [
            'id', 'provedor', 'api_id', 'api_hash', 'phone_number',
            'is_active', 'is_connected', 'last_sync', 'settings', 'created_at',
            'session_string', 'telegramInfo'
        ]
        read_only_fields = ['id', 'session_string', 'is_connected', 'last_sync', 'created_at']
        extra_kwargs = {
            'api_hash': {'write_only': True}
        }

    def get_telegramInfo(self, obj):
        """
        Monta bloco telegramInfo para o front usar.
        """
        data = {}

        # Se integração ainda não conectou
        if not obj.is_connected:
            return {
                "status": "disconnected",
                "reason": "not_connected"
            }

        extras = obj.dados_extras or {}

        tg_user = extras.get("telegram_user", {})
        tg_photo = extras.get("telegram_photo")

        return {
            "status": "connected",
            "user_id": tg_user.get("id"),
            "name": tg_user.get("name"),
            "username": tg_user.get("username"),
            "phone": tg_user.get("phone"),
            "profile_photo": tg_photo,   # base64 direto
        }


# ============================================================
#   EMAIL SERIALIZER
# ============================================================

class EmailIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailIntegration
        fields = [
            'id', 'provedor', 'name', 'email', 'provider',
            'imap_host', 'imap_port', 'imap_use_ssl',
            'smtp_host', 'smtp_port', 'smtp_use_tls',
            'username', 'is_active', 'is_connected',
            'last_sync', 'settings', 'created_at'
        ]
        read_only_fields = ['id', 'is_connected', 'last_sync', 'created_at']
        extra_kwargs = {
            'password': {'write_only': True}
        }


# ============================================================
#   WHATSAPP SERIALIZER
# ============================================================

class WhatsAppIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppIntegration
        fields = [
            'id', 'provedor', 'phone_number', 'webhook_url',
            'is_active', 'is_connected', 'last_sync',
            'settings', 'created_at'
        ]
        read_only_fields = ['id', 'is_connected', 'last_sync', 'created_at']
        extra_kwargs = {
            'access_token': {'write_only': True},
            'verify_token': {'write_only': True}
        }


# ============================================================
#   WEBCHAT SERIALIZER
# ============================================================

class WebchatIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebchatIntegration
        fields = [
            'id', 'provedor', 'widget_color', 'welcome_message',
            'pre_chat_form_enabled', 'pre_chat_form_options',
            'business_hours', 'is_active', 'settings', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
