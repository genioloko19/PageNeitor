@echo off
chcp 65001 >nul
echo ===================================================
echo   Compilando Pageneitor a Ejecutable Windows (.exe)
echo ===================================================
python build_windows.py
if errorlevel 1 (
  echo.
  echo La compilacion no se completo. Revisa el mensaje anterior.
)
echo.
echo Presiona cualquier tecla para salir...
pause >nul
