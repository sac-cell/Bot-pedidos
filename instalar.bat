@echo off
title Instalador Bot Pedidos
color 0A

echo ========================================
echo    INSTALADOR BOT PEDIDOS
echo ========================================
echo.

REM Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python NAO encontrado!
    echo.
    echo O Python e necessario para rodar o bot.
    echo.
    echo OPCAO 1 - Rode o arquivo "Bot Pedidos.exe" (nao precisa de Python)
    echo.
    echo OPCAO 2 - Instale o Python:
    echo   1. Acesse: https://www.python.org/downloads/
    echo   2. Clique em "Download Python 3.11.9"
    echo   3. AO INSTALAR, marque a caixa "Add Python to PATH"
    echo   4. Depois rode este arquivo novamente
    echo.
    pause
    exit /b
)

echo [OK] Python encontrado!
echo.

echo [1/2] Instalando playwright...
python -m pip install playwright
if errorlevel 1 (
    echo [X] Erro ao instalar playwright!
    pause
    exit /b
)
echo [OK] Playwright instalado!
echo.

echo [2/2] Instalando navegador (chromium)...
echo Isso pode demorar alguns minutos...
python -m playwright install chromium
if errorlevel 1 (
    echo [X] Erro ao instalar chromium!
    pause
    exit /b
)
echo [OK] Chromium instalado!
echo.

echo ========================================
echo    INSTALACAO COMPLETA!
echo ========================================
echo.
echo Para usar o bot:
echo   python bot_pedidos.py
echo.
echo OU execute o arquivo "Bot Pedidos.exe"
echo.
pause
