@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 goto iniciar_py
where python >nul 2>&1
if not errorlevel 1 goto iniciar_python
echo Python 3.10 ou superior nao localizado. O programa nao inclui interpretador.
echo Instale Python no perfil do usuario, sem necessidade de administrador.
pause
goto :eof
:iniciar_py
py -3 -m poe_truss.server
if errorlevel 1 pause
goto :eof
:iniciar_python
python -m poe_truss.server
if errorlevel 1 pause
goto :eof
