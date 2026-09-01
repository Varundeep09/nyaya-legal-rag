import sys
import os
import asyncio
from arq import run_worker

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from app.workers.document_worker import WorkerSettings

if __name__ == "__main__":
    asyncio.run(run_worker(WorkerSettings))
