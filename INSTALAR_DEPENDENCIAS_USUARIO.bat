@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install --user -r requirements-desktop.txt
if errorlevel 1 (
 echo Falha ao instalar em modo usuario. Verifique Python, pip, rede e politica da empresa.
 pause
 exit /b 1
)
echo Instalacao concluida no perfil do usuario.
pause
endlocal
