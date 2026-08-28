@echo off
cd /d %~dp0
echo Executando migracoes...
python manage.py migrate
echo.
echo Criando superadmin...
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); username='Junior'; password='Senfim01@'; user_type='superadmin'; user, created = User.objects.get_or_create(username=username, defaults={'user_type': user_type, 'is_staff': True, 'is_superuser': True}); user.set_password(password); user.user_type=user_type; user.is_staff=True; user.is_superuser=True; user.save(); print('Usuario criado/atualizado com sucesso!' if not created else 'Usuario atualizado com sucesso!')"
pause






