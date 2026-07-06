@echo off
chcp 65001 >nul
echo ========================================
echo    INSTALADOR BOT PEDIDOS
echo ========================================
echo.

REM Verifica se Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [1/4] Python nao encontrado. Baixando...
    echo Isso pode demorar alguns minutos.
    echo.
    
    REM Baixa o instalador do Python
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\python-installer.exe'}"
    
    if not exist "%TEMP%\python-installer.exe" (
        echo [ERRO] Falha ao baixar Python!
        echo Baixe manualmente em: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    
    echo [2/4] Instalando Python (pode pedir permissao do administrador)...
    "%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    
    if errorlevel 1 (
        echo [AVISO] Instalacao do Python pode ter falhado.
        echo Tentando continuar...
    )
    
    REM Aguarda um pouco para finalizar
    timeout /t 5 /nobreak >nul
    
    REM Atualiza PATH nesta sessao
    set "PATH=%PATH%;C:\Program Files\Python311;C:\Program Files\Python311\Scripts"
    
    del "%TEMP%\python-installer.exe" >nul 2>&1
) else (
    echo [1/4] Python encontrado!
)

echo.
echo [2/4] Instalando dependencias...
python -m pip install --upgrade pip -q
python -m pip install playwright -q

echo.
echo [3/4] Instalando navegador (chromium)...
python -m playwright install chromium

echo.
echo [4/4] Configuracao concluida!
echo.
echo ========================================
echo    INSTALACAO COMPLETA!
echo ========================================
echo.
echo Para usar o bot agora, execute:
echo    python bot_pedidos.py
echo.
echo OU clique duas vezes no arquivo "Bot Pedidos.exe"
echo.
pause
