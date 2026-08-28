from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0021_team_horarios_atendimento'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='message',
            index=models.Index(
                fields=['conversation', '-created_at'],
                name='msg_conv_created_desc_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(
                fields=['conversation', 'is_from_customer', '-created_at'],
                name='msg_conv_cust_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(
                fields=['inbox', 'status', '-last_message_at'],
                name='conv_inbox_status_lastmsg_idx',
            ),
        ),
    ]
