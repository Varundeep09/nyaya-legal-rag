"""
Worker entrypoint module aliasing WorkerSettings from document_worker.
"""

from app.workers.document_worker import WorkerSettings, process_user_document

__all__ = ["WorkerSettings", "process_user_document"]
