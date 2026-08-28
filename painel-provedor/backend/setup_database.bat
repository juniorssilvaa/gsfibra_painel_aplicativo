@echo off
cd /d %~dp0
echo ========================================
echo Executando migracoes do banco de dados
echo ========================================
python manage.py migrate
echo.
echo ========================================
echo Criando superadmin
echo ========================================
python manage.py shell < create_superadmin_script.py
echo.
echo ========================================
echo Concluido!
echo ========================================
pause






