Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   INSTALADOR BOT PEDIDOS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verifica Python
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    Write-Host "Python encontrado!" -ForegroundColor Green
} else {
    Write-Host "Python nao encontrado. Baixando..." -ForegroundColor Yellow
    Write-Host "Isso pode demorar 1-2 minutos."
    Write-Host ""
    
    $url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    $installer = "$env:TEMP\python-installer.exe"
    
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        Write-Host "ERRO: Nao foi possivel baixar o Python!" -ForegroundColor Red
        Write-Host "Baixe manualmente: https://www.python.org/downloads/"
        Read-Host "Pressione ENTER para sair"
        exit 1
    }
    
    Write-Host "Instalando Python..." -ForegroundColor Yellow
    Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
    
    $env:PATH = "$env:PATH;C:\Program Files\Python311;C:\Program Files\Python311\Scripts"
    
    Write-Host "Python instalado!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Instalando playwright..." -ForegroundColor Yellow
& python -m pip install playwright -q

Write-Host "Instalando navegador..." -ForegroundColor Yellow
& python -m playwright install chromium

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   INSTALACAO COMPLETA!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Para usar o bot, execute:"
Write-Host "   python bot_pedidos.py" -ForegroundColor Cyan
Write-Host ""
Read-Host "Pressione ENTER para fechar"
