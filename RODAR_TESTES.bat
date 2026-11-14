@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 goto teste_py
where python >nul 2>&1
if not errorlevel 1 goto teste_python
echo Python nao localizado.
pause
goto :eof
:teste_py
py -3 -m unittest discover -s tests -v
pause
goto :eof
:teste_python
python -m unittest discover -s tests -v
pause
goto :eof
