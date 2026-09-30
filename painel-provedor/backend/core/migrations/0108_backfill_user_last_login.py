from django.db import migrations
from django.db.models import Max


def backfill_last_login(apps, schema_editor):
    User = apps.get_model('core', 'User')
    AuditLog = apps.get_model('core', 'AuditLog')

    ultimos = (
        AuditLog.objects.filter(action='login', user__isnull=False, user__last_login__isnull=True)
        .values('user_id')
        .annotate(ultimo=Max('timestamp'))
    )
    for row in ultimos:
        User.objects.filter(pk=row['user_id'], last_login__isnull=True).update(last_login=row['ultimo'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0107_agentpushdevice'),
    ]

    operations = [
        migrations.RunPython(backfill_last_login, migrations.RunPython.noop),
    ]
