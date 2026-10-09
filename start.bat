@echo off
REM ======================================================================
REM  Xadrez - Edicao de Clube  ::  inicia o servidor local
REM  Basta dar dois cliques neste arquivo. NAO precisa instalar nada.
REM ======================================================================
cd /d "%~dp0"
setlocal

echo.
echo === Xadrez - Edicao de Clube ===
echo.

REM Descobre o interpretador: python ou o lancador py
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY (
  where py >nul 2>&1 && set "PY=py"
)
if not defined PY (
  echo [ERRO] Python nao encontrado no PATH.
  echo Instale em https://www.python.org/downloads/ e marque "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

echo Usando: %PY%
%PY% --version
echo.

echo ---------------------------------------------------------------
echo   Abra no navegador:  http://127.0.0.1:8000
echo   Para parar:         Ctrl + C
echo ---------------------------------------------------------------
echo.

REM Servidor sem dependencias (so biblioteca padrao do Python).
%PY% server_stdlib.py

echo.
echo Servidor encerrado.
pause
