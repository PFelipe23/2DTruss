@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import PySide6, ezdxf" >nul 2>&1
if errorlevel 1 (
    echo [2DTruss] PySide6 ou ezdxf nao estao instalados neste Python.
    echo Execute INSTALAR_DEPENDENCIAS_USUARIO.bat, sem permissao de administrador.
    pause
    exit /b 1
)
py -3 2DTruss.pyw
if errorlevel 1 pause
endlocal
