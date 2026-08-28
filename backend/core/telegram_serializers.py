# ==============================================
# TELEGRAM SERIALIZER OFICIAL DO NIOCHAT
# ==============================================

from rest_framework import serializers

from integrations.models import TelegramIntegration


class TelegramInfoSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    username = serializers.CharField(required=False, allow_null=True)
    name = serializers.CharField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_null=True)
    profile_photo = serializers.CharField(required=False, allow_null=True)


class TelegramIntegrationSerializer(serializers.ModelSerializer):
    telegramInfo = serializers.SerializerMethodField()
    session_string = serializers.CharField(read_only=True)

    class Meta:
        model = TelegramIntegration
        fields = [
            'id', 'provedor', 'api_id', 'api_hash', 'phone_number',
            'is_active', 'is_connected', 'last_sync', 'settings',
            'created_at', 'session_string', 'telegramInfo'
        ]
        read_only_fields = ['id', 'session_string', 'is_connected', 'last_sync', 'created_at']
        extra_kwargs = {
            'api_hash': {'write_only': True}
        }

    def get_telegramInfo(self, obj):
        """
        Constrói o bloco telegramInfo consumido pelo FRONT.
        Puxa as infos salvas no settings do TelegramIntegration.
        """
        if not obj.is_connected:
            return {
                "status": "disconnected",
                "reason": "not_connected"
            }

        extras = obj.settings or {}

        tg_user = extras.get("telegram_user", {})
        tg_photo = extras.get("telegram_photo")

        return {
            "status": "connected",
            "id": tg_user.get("id") or tg_user.get("telegram_id"),
            "username": tg_user.get("username"),
            "name": tg_user.get("name") or tg_user.get("first_name"),
            "phone": tg_user.get("phone"),
            "profile_photo": tg_photo,
        }

