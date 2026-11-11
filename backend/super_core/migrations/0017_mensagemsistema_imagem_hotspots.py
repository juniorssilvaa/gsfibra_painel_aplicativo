from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0016_billingsendlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='mensagemsistema',
            name='imagem_url',
            field=models.URLField(blank=True, default='', max_length=1000),
        ),
        migrations.AddField(
            model_name='mensagemsistema',
            name='hotspots',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Áreas clicáveis na imagem: [{x,y,w,h,url,label}] em % (0-100).',
            ),
        ),
        migrations.AddField(
            model_name='mensagemsistema',
            name='cta_links',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Botões abaixo da imagem: [{label,url}].',
            ),
        ),
    ]
