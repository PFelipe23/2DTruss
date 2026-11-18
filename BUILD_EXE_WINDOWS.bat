@echo off
setlocal
cd /d "%~dp0" || exit /b 1
set "PY_LAUNCHER_ARGS="

if defined BUILD_PYTHON goto build
if defined VIRTUAL_ENV (
    set "BUILD_PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
) else (
    set "BUILD_PYTHON=py"
    set "PY_LAUNCHER_ARGS=-3.12"
)

:build
rem Restrict DLL discovery to the build environment and Windows system paths.
set "PATH=%SystemRoot%\System32;%SystemRoot%"
set "PYINSTALLER_CONFIG_DIR=%~dp0build\pyinstaller-cache"
"%BUILD_PYTHON%" %PY_LAUNCHER_ARGS% -m PyInstaller ^
    --noconfirm --clean --windowed --onedir --noupx --name 2DTruss_v0.1 ^
    --specpath build ^
    --additional-hooks-dir "%~dp0scripts\pyinstaller" ^
    --copy-metadata PySide6-Essentials --copy-metadata shiboken6 ^
    --copy-metadata ezdxf --copy-metadata numpy --copy-metadata fonttools ^
    --copy-metadata pyparsing --copy-metadata typing-extensions ^
    --add-data "%~dp0LICENSE:." ^
    --add-data "%~dp0docs\LICENCIAMENTO.md:." ^
    --add-data "%~dp0catalogo_perfis.csv:." ^
    --add-data "%~dp0examples\cobertura_duas_aguas.json:examples" ^
    --add-data "%~dp0examples\FTool_A02_trelica_triangular.json:examples" ^
    --add-data "%~dp0examples\trelica_triangular_analitica_dxf_mm.dxf:examples" ^
    2DTruss.pyw
if errorlevel 1 exit /b 1

echo Saida: dist\2DTruss_v0.1\2DTruss_v0.1.exe
