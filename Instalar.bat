@echo off
title Instalador do gerador de videos
cd /d "%~dp0"
rem Instala tudo o que o app precisa (pode rodar de novo quando quiser).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pipeline\instalar.ps1"
pause
