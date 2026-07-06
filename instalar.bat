@echo off
chcp 65001 >nul
echo ========================================
echo    INSTALADOR BOT PEDIDOS
echo ========================================
echo.

REM Verifica se Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado!
    echo Baixe em: https://www.python.org/downloads/
    echo Marque a opcao "Add Python to PATH" durante a instalacao!
    pause
    exit /b 1
)

echo [1/3] Instalando dependencias...
pip install playwright -q

echo [2/3] Instalando navegador...
python -m playwright install chromium

echo [3/3] Configuracao concluida!
echo.
echo ========================================
echo    INSTALACAO COMPLETA!
echo ========================================
echo.
echo Para usar o bot, execute:
echo    python bot_pedidos.py
echo.
pause
