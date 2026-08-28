@echo off
chcp 65001 >nul
cd /d %~dp0
echo ========================================
echo Executando migracoes do banco de dados
echo ========================================
python manage.py migrate
if errorlevel 1 (
    echo ERRO ao executar migracoes!
    pause
    exit /b 1
)
echo.
echo ========================================
echo Criando superadmin
echo ========================================
python manage.py create_superadmin_custom --username Junior --password Senfim01@ --user-type superadmin
if errorlevel 1 (
    echo ERRO ao criar superadmin!
    pause
    exit /b 1
)
echo.
echo ========================================
echo Concluido com sucesso!
echo ========================================
echo.
echo Credenciais de acesso:
echo Usuario: Junior
echo Senha: Senfim01@
echo Tipo: superadmin
echo.
pause






