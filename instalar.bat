@echo off
echo ========================================
echo    INSTALADOR BOT PEDIDOS
echo ========================================
echo.

echo Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python nao encontrado! Baixando automaticamente...
    echo Isso pode demorar 1-2 minutos.
    echo.
    
    curl -L -o "%TEMP%\python-installer.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    
    if not exist "%TEMP%\python-installer.exe" (
        echo.
        echo ERRO: Nao foi possivel baixar o Python!
        echo Baixe manualmente: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    
    echo Instalando Python (pode pedir permissao)...
    "%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    timeout /t 15 /nobreak >nul
    del "%TEMP%\python-installer.exe" >nul 2>&1
    
    set "PATH=%PATH%;C:\Program Files\Python311;C:\Program Files\Python311\Scripts"
    
    echo Python instalado!
) else (
    echo Python encontrado!
)

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
