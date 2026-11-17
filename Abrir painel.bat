@echo off
title Painel de videos
cd /d "%~dp0"
set ARGS=
:inicio
python -I pipeline\painel.py %ARGS%
rem Codigo 3 = o painel foi atualizado e pediu para reabrir (sem abrir outra aba no navegador)
if %errorlevel%==3 (
  set ARGS=--sem-navegador
  echo.
  echo Reabrindo o painel com a versao nova...
  goto inicio
)
pause
