from django.db import migrations, models
import django.db.models.deletion


def add_canal_if_not_exists(apps, schema_editor):
    table_name = 'core_chatbotflow'
    column_name = 'canal_id'
    
    # Check if column exists
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == 'postgresql':
            cursor.execute(
                "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = %s AND column_name = %s)",
                [table_name, column_name]
            )
            exists = cursor.fetchone()[0]
        else:
            # SQLite / other vendors
            cursor.execute(f"PRAGMA table_info({table_name})")
            exists = any(row[1] == column_name for row in cursor.fetchall())
    
    if not exists:
        # Get historical models
        ChatbotFlow = apps.get_model('core', 'ChatbotFlow')
        Canal = apps.get_model('core', 'Canal')
        
        # Create the field instance
        field = models.ForeignKey(
            to=Canal,
            on_delete=django.db.models.deletion.SET_NULL,
            null=True,
            blank=True,
            related_name='chatbot_flows',
            verbose_name='Canal'
        )
        field.set_attributes_from_name('canal')
        
        # Add the field using schema_editor
        schema_editor.add_field(ChatbotFlow, field)

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0066_user_volumes'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='chatbotflow',
                    name='canal',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chatbot_flows', to='core.canal', verbose_name='Canal'),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_canal_if_not_exists, reverse_code=migrations.RunPython.noop),
            ]
        )
    ]
