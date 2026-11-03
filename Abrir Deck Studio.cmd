@echo off
rem Abre o Deck Studio no navegador. Fechar esta janela encerra o app.
cd /d "%~dp0"
title Deck Studio
".venv\Scripts\python.exe" -m deck_studio %*
pause
