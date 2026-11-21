@echo off
rem Ejecuta Python 3.9+ con el nombre que tenga este equipo: python, py o python3.
rem (El "python" de la Microsoft Store sin instalar no cuenta: falla la prueba y se pasa al siguiente.)
set "KIT_PY="
for %%P in ("python" "py -3" "python3") do if not defined KIT_PY (
    %%~P -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1 && set "KIT_PY=%%~P"
)
if not defined KIT_PY goto nopython
%KIT_PY% %*
exit /b %errorlevel%

:nopython
echo.
echo No encuentro Python 3.9 o superior en este equipo.
echo Instalalo gratis desde https://www.python.org/downloads/
echo marcando "Add python.exe to PATH", cierra y vuelve a abrir VS Code.
exit /b 1