@echo off
cd /d %~dp0
python manage.py migrate
pause






