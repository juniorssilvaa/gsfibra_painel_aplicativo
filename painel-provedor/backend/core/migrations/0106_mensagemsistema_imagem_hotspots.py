from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0105_canal_disparo_resposta_acao'),
    ]

    operations = [
        migrations.AddField(
            model_name='mensagemsistema',
            name='imagem_url',
            field=models.URLField(blank=True, default='', max_length=1000, verbose_name='URL da imagem'),
        ),
        migrations.AddField(
            model_name='mensagemsistema',
            name='hotspots',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='[{x,y,w,h,url,label}] em % (0-100).',
                verbose_name='Áreas clicáveis na imagem',
            ),
        ),
        migrations.AddField(
            model_name='mensagemsistema',
            name='cta_links',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='[{label,url}].',
                verbose_name='Botões / links',
            ),
        ),
    ]
