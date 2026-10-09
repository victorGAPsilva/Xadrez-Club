#!/usr/bin/env bash
# =====================================================================
#  Xadrez - Edicao de Clube  ::  inicia o servidor local
#  Nao precisa instalar nada (usa so a biblioteca padrao do Python).
# =====================================================================
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[ERRO] Python nao encontrado. Instale o Python 3.10+."
  exit 1
fi

echo
echo "=== Xadrez - Edicao de Clube ==="
"$PY" --version
echo
echo "---------------------------------------------------------------"
echo "  Abra no navegador:  http://127.0.0.1:8000"
echo "  Para parar:         Ctrl + C"
echo "---------------------------------------------------------------"
echo

exec "$PY" server_stdlib.py
