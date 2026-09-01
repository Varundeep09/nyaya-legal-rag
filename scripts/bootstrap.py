"""
Bootstrap runner for Nyaya Legal Assistant:
Waits for database connectivity, then executes statute ingestion, schedule ingestion, and forms extraction in order.
"""

import sys
import os
import time
import subprocess
import socket

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

def wait_for_db(host="postgres", port=5432, timeout=60):
    start = time.time()
    print(f"[1/4] Checking PostgreSQL connection ({host}:{port})...")
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                print("PostgreSQL is connected and reachable.")
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(2)
    print("Warning: PostgreSQL wait timed out, continuing...")
    return False

def run_step(desc, cmd):
    print(f"\n---> {desc}")
    start = time.time()
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"Error in step: {desc} (Exit code {res.returncode})")
        sys.exit(res.returncode)
    elapsed = time.time() - start
    print(f"Completed in {elapsed:.1f}s.")

if __name__ == "__main__":
    db_host = os.environ.get("POSTGRES_SERVER", "localhost")
    db_port = int(os.environ.get("POSTGRES_PORT", 5432))
    
    wait_for_db(host=db_host, port=db_port)
    
    python_bin = sys.executable
    run_step("[2/4] Ingesting BNSS Bare Act (531 sections)...", f'"{python_bin}" -m scripts.ingest_bns --with-embeddings')
    run_step("[3/4] Ingesting BNS First Schedule (531 rows)...", f'"{python_bin}" -m scripts.ingest_schedule --with-embeddings')
    run_step("[4/4] Extracting 58 Statutory Vector Forms...", f'"{python_bin}" -m scripts.extract_forms')
    
    print("\n=== Bootstrap Finished Successfully! ===")
