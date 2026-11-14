@echo off
setlocal
cd /d "%~dp0"
rem Comando opcional para criar EXE localmente. Nao usa direitos de administrador.
py -3 -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
 echo PyInstaller nao instalado. Utilize py -3 -m pip install --user pyinstaller
 pause
 exit /b 1
)
py -3 -m PyInstaller --noconfirm --clean --windowed --onedir --name 2DTruss_v0.1 --collect-all ezdxf --add-data "catalogo_perfis.csv;." --add-data "examples;examples" 2DTruss.pyw
if errorlevel 1 (
 echo Falha na compilacao. Consulte os logs e dependencias.
 pause
 exit /b 1
)
echo Saida: dist\2DTruss_v0.1
pause
endlocal
