@echo off
echo ========================================
echo    INSTALADOR BOT PEDIDOS
echo ========================================
echo.

echo Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERRO] Python nao encontrado!
    echo.
    echo Baixe o Python em:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: Marque a opcao "Add Python to PATH"!
    echo Depois de instalar, rode este arquivo novamente.
    echo.
    pause
    exit /b 1
)

echo Python encontrado!
echo.
echo Instalando playwright...
python -m pip install playwright -q

echo Instalando navegador...
python -m playwright install chromium

echo.
echo ========================================
echo    INSTALACAO COMPLETA!
echo ========================================
echo.
echo Para usar o bot, execute:
echo    python bot_pedidos.py
echo.
pause
