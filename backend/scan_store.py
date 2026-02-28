"""
scan_store.py — In-memory store for async scan jobs.

Instead of SSE (which Render's proxy kills after 90s), the frontend
polls GET /api/scan/status/<job_id> every second.

Flow:
  1. POST /api/scan/start  → returns { job_id }  immediately
  2. Background thread runs the scan, updates job state
  3. Frontend polls GET /api/scan/status/<job_id> every second
  4. Each poll returns { status, progress, results_so_far }
  5. When status == "done", frontend stops polling
"""

import uuid
import threading
import time
import logging

log = logging.getLogger(__name__)

# { job_id: { status, total, completed, matches, error } }
_jobs: dict = {}
_lock = threading.Lock()


def create_job() -> str:
    job_id = str(uuid.uuid4())[:8]
    with _lock:
        _jobs[job_id] = {
            "status": "running",
            "total": 0,
            "completed": 0,
            "matches": [],
            "error": None,
            "created_at": time.time(),
        }
    return job_id


def get_job(job_id: str) -> dict | None:
    with _lock:
        return dict(_jobs.get(job_id, {}))


def update_progress(job_id: str, completed: int, total: int):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["completed"] = completed
            _jobs[job_id]["total"] = total


def add_match(job_id: str, result: dict):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["matches"].append(result)


def finish_job(job_id: str):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "done"


def fail_job(job_id: str, error: str):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = error


def cleanup_old_jobs():
    """Remove jobs older than 10 minutes to free memory."""
    cutoff = time.time() - 600
    with _lock:
        old = [jid for jid, j in _jobs.items() if j["created_at"] < cutoff]
        for jid in old:
            del _jobs[jid]
