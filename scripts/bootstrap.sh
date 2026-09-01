#!/usr/bin/env bash
set -e

echo "=== [Nyaya Legal Assistant] Starting Database & Corpus Bootstrap ==="

# 1. Wait for PostgreSQL to be ready
echo "[1/4] Waiting for PostgreSQL database..."
until python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('postgres', 5432))
    s.close()
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; do
    echo "PostgreSQL is unavailable - sleeping 2 seconds..."
    sleep 2
done
echo "PostgreSQL is UP and ready."

# 2. Ingest BNSS Bare Act with Dense Vectors
echo "[2/4] Ingesting BNSS Bare Act (531 sections, 39 chapters)..."
python -m scripts.ingest_bns --with-embeddings

# 3. Ingest First Schedule Offence Classifications
echo "[3/4] Ingesting BNS Offence Classification Schedule (531 rows)..."
python -m scripts.ingest_schedule --with-embeddings

# 4. Extract Statutory Forms (Second Schedule)
echo "[4/4] Extracting 58 Statutory Vector Forms..."
python -m scripts.extract_forms

echo "=== [Nyaya Legal Assistant] Bootstrap Successfully Completed! ==="
