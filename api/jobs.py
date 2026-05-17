"""
Render-job lifecycle. Backed by Mongo so jobs survive process restarts and
are visible to the user across reloads.

Status flow:  queued -> running -> done | failed | cancelled
              blocked (over free-tier limit, won't run until plan changes)
"""

from __future__ import annotations

import os
import threading
import time
import traceback
from datetime import datetime, timezone
from queue import Queue
from typing import Any, Callable, Optional

from bson import ObjectId


# How many jobs run in parallel. Override with WORKER_CONCURRENCY env var.
# 3 is the sweet spot for Gemini per-key rate limits.
WORKER_CONCURRENCY = max(1, int(os.environ.get("WORKER_CONCURRENCY", "3")))


# ---- Cancellation -------------------------------------------------------
#
# Two layers, both required for a clean cancel of a long-running job:
#   1) Mongo flag. The handler reads `is_cancelled(job_id)` at every safe
#      checkpoint between steps. If true, raise CancelledError.
#   2) Live subprocess registry. While ffmpeg is encoding, the only way to
#      stop it is to send a signal to the OS process. Handlers register
#      each Popen they spawn so the cancel endpoint can kill them.

class CancelledError(RuntimeError):
    """Raised by handlers to short-circuit when a cancel was requested."""


_CANCEL_PROCS: dict[str, set] = {}
_CANCEL_PROCS_LOCK = threading.Lock()


def register_proc(job_id: str, proc) -> None:
    """Track a Popen so the cancel endpoint can kill it later."""
    with _CANCEL_PROCS_LOCK:
        _CANCEL_PROCS.setdefault(job_id, set()).add(proc)


def unregister_proc(job_id: str, proc) -> None:
    with _CANCEL_PROCS_LOCK:
        bucket = _CANCEL_PROCS.get(job_id)
        if bucket is not None:
            bucket.discard(proc)
            if not bucket:
                _CANCEL_PROCS.pop(job_id, None)


def kill_procs(job_id: str) -> int:
    """Best-effort kill of every live subprocess registered for this job."""
    with _CANCEL_PROCS_LOCK:
        bucket = _CANCEL_PROCS.pop(job_id, set())
    n = 0
    for p in bucket:
        try:
            p.kill()
            n += 1
        except Exception:
            pass
    return n


def is_cancelled(job_id: str) -> bool:
    """Cheap polling check the handler calls between steps."""
    doc = _coll().find_one({"_id": ObjectId(job_id)}, {"status": 1, "cancelRequested": 1})
    if not doc:
        return False
    return bool(doc.get("cancelRequested")) or doc.get("status") == "cancelled"


def raise_if_cancelled(job_id: str) -> None:
    if is_cancelled(job_id):
        raise CancelledError("cancelled by user")


def request_cancel(job_id: str, user_id: Optional[str] = None) -> dict:
    """
    Mark a job as cancelled. If running, kill its ffmpeg children too.
    Idempotent — calling on an already-final job is a no-op.
    Returns a small status payload.
    """
    q: dict[str, Any] = {"_id": ObjectId(job_id)}
    if user_id is not None:
        q["userId"] = user_id
    doc = _coll().find_one(q)
    if not doc:
        return {"ok": False, "reason": "not_found"}

    status = doc.get("status")
    if status in ("done", "failed", "cancelled"):
        return {"ok": True, "alreadyFinal": True, "status": status}

    # Flip the status to "cancelled" immediately for BOTH queued and
    # running jobs. The worker's checkpoints (raise_if_cancelled) may
    # take a few seconds to notice — especially mid-Gemini-call — so if
    # we leave status="running" the UI keeps showing it in the in-progress
    # tab. By marking cancelled now, the user gets instant feedback and
    # the worker still does its cleanup, just async.
    update_job(
        job_id,
        cancelRequested=True,
        status="cancelled",
        message="Cancelled",
    )
    killed = kill_procs(job_id) if status == "running" else 0
    return {"ok": True, "killed": killed, "wasStatus": status}


# ---------- Mongo helpers ---------------------------------------------------

def _coll():
    """Lazy-import to avoid circular imports at startup."""
    from app import db
    return db().tool_jobs


def create_job(
    *,
    user_id: str,
    tool: str,
    params: dict[str, Any],
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
) -> str:
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "userId": user_id,
        "tool": tool,
        "params": params,
        "status": "queued",
        "progress": 0,
        "message": None,
        "outputPath": None,
        "outputContentType": None,
        "errorDetail": None,
        "createdAt": now,
        "updatedAt": now,
    }
    # Top-level project fields so /me/projects can index/group cheaply
    # without parsing nested params on every job.
    if project_id:
        doc["projectId"] = project_id
    if project_name:
        doc["projectName"] = project_name
    res = _coll().insert_one(doc)
    return str(res.inserted_id)


def get_job(job_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    try:
        oid = ObjectId(job_id)
    except Exception:
        return None
    q: dict[str, Any] = {"_id": oid}
    if user_id is not None:
        q["userId"] = user_id
    return _coll().find_one(q)


def update_job(job_id: str, **fields) -> None:
    fields["updatedAt"] = datetime.now(timezone.utc)
    _coll().update_one({"_id": ObjectId(job_id)}, {"$set": fields})


def serialize_job(doc: dict) -> dict:
    params = doc.get("params") or {}
    active_cap = doc.get("activeCaptionsJobId")
    return {
        "id": str(doc["_id"]),
        "tool": doc["tool"],
        "status": doc["status"],
        "progress": int(doc.get("progress", 0)),
        "message": doc.get("message"),
        "params": params,
        "audioFilename": params.get("audioFilename"),
        "label": params.get("label"),
        "hasOutput": bool(doc.get("outputPath")),
        "errorDetail": doc.get("errorDetail"),
        "workerName": doc.get("workerName"),
        "cancelRequested": bool(doc.get("cancelRequested")),
        # Captions augmentation — only set on parent audio-to-video jobs.
        "activeCaptionsJobId": str(active_cap) if active_cap else None,
        "activeCaptionsStyle": doc.get("activeCaptionsStyle"),
        # Source-video metadata for transcribe-only bulk-captions jobs;
        # the editor needs these to size and seek the overlay correctly.
        "videoWidth": int(doc["videoWidth"]) if doc.get("videoWidth") else None,
        "videoHeight": int(doc["videoHeight"]) if doc.get("videoHeight") else None,
        "videoDuration": float(doc["videoDuration"]) if doc.get("videoDuration") else None,
        # Per-frame quality breakdown for audio-to-video jobs. Lets the UI
        # surface "X of Y frames used fallback" instead of silently
        # showing placeholders.
        "frameQuality": doc.get("frameQuality"),
        # Project grouping (added 2026-05). Top-level fields so the UI
        # can group recent jobs into folders without parsing params.
        "projectId": doc.get("projectId"),
        "projectName": doc.get("projectName"),
        "createdAt": _iso(doc.get("createdAt")),
        "updatedAt": _iso(doc.get("updatedAt")),
    }


def _iso(d: Any) -> Optional[str]:
    if isinstance(d, datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.isoformat()
    return None


# ---------- In-process worker queue -----------------------------------------

# We use a process-local queue. Single-process deployments are fine for
# v1; when we scale we'll swap this for Redis + RQ without touching the
# endpoint surface (the Mongo doc is the contract).

JobHandler = Callable[[str, str, dict[str, Any]], None]
"""(job_id, user_id, params) -> None. Should call update_job() liberally
and raise to fail the job. The worker catches exceptions and writes a
failed status with the traceback."""

_HANDLERS: dict[str, JobHandler] = {}


def register_handler(tool: str, handler: JobHandler) -> None:
    _HANDLERS[tool] = handler


_QUEUE: "Queue[tuple[str, str]]" = Queue()


def enqueue(job_id: str, user_id: str) -> None:
    _QUEUE.put((job_id, user_id))


def _process_one(job_id: str, user_id: str, worker_name: str) -> None:
    """Run exactly one job to completion. Caller is the worker thread."""
    try:
        doc = get_job(job_id)
        if not doc:
            return

        # If a queued job was cancelled before we picked it up, skip it.
        if doc.get("status") in ("cancelled",) or doc.get("cancelRequested"):
            update_job(
                job_id,
                status="cancelled",
                message="Cancelled before start",
            )
            return

        handler = _HANDLERS.get(doc["tool"])
        if not handler:
            update_job(
                job_id,
                status="failed",
                errorDetail=f"No handler registered for tool={doc['tool']}",
            )
            return

        update_job(
            job_id,
            status="running",
            progress=1,
            message="Starting…",
            workerName=worker_name,
        )
        handler(job_id, user_id, doc.get("params") or {})

        # If the user cancelled mid-flight while the handler was inside a
        # non-cancellable call (e.g. a Gemini retry), the doc is already
        # `cancelled` — don't clobber it with done.
        current = get_job(job_id)
        if not current:
            return
        if current["status"] == "cancelled" or current.get("cancelRequested"):
            update_job(
                job_id,
                status="cancelled",
                message="Cancelled by user",
            )
            return
        if current["status"] == "running":
            update_job(job_id, status="done", progress=100, message="Done")

    except CancelledError:
        # Clean cancel — never mark as failed, just record the final state.
        try:
            update_job(
                job_id,
                status="cancelled",
                message="Cancelled by user",
            )
        except Exception:
            pass

    except Exception as e:
        tb = traceback.format_exc()
        try:
            update_job(
                job_id,
                status="failed",
                errorDetail=str(e) + "\n\n" + tb,
            )
        except Exception:
            print(f"[worker] failed to mark job {job_id} as failed: {tb}")
    finally:
        # Always drop any lingering process registrations for this job —
        # otherwise a future cancel call could try to kill stale handles.
        with _CANCEL_PROCS_LOCK:
            _CANCEL_PROCS.pop(job_id, None)


def _worker_loop(worker_name: str):
    while True:
        job_id, user_id = _QUEUE.get()
        try:
            _process_one(job_id, user_id, worker_name)
        finally:
            _QUEUE.task_done()


_started = False


def _heal_stale_running() -> None:
    """
    Any job left in `running` at startup belongs to a worker process that
    died (server crash / restart). Without this sweep, those jobs sit in
    the UI as "70% Burning captions…" forever. We fail them with a clear
    message so the user can resubmit instead of waiting on a ghost.
    """
    try:
        n = _coll().update_many(
            {"status": "running"},
            {"$set": {
                "status": "failed",
                "errorDetail": (
                    "Worker died during render (server restart). "
                    "Re-submit to retry."
                ),
                "updatedAt": datetime.now(timezone.utc),
            }},
        ).modified_count
        if n:
            print(f"[jobs] healed {n} stale running job(s) on startup")
    except Exception as e:
        # Non-fatal — worse case is one stale job stays until next restart.
        print(f"[jobs] heal_stale_running failed: {e}")


def start_worker_thread():
    """
    Spawn the worker pool. Idempotent — calling twice is a no-op so it
    survives FastAPI lifespan re-runs in dev.
    """
    global _started
    if _started:
        return
    _started = True
    _heal_stale_running()
    for i in range(WORKER_CONCURRENCY):
        name = f"job-worker-{i+1}"
        t = threading.Thread(target=_worker_loop, args=(name,), daemon=True, name=name)
        t.start()
    print(f"[jobs] started {WORKER_CONCURRENCY} worker thread(s)")


def list_user_jobs(user_id: str, limit: int = 100, status: Optional[str] = None) -> list[dict]:
    """Newest-first list of a user's jobs, optionally filtered by status."""
    q: dict[str, Any] = {"userId": user_id}
    if status:
        q["status"] = status
    cursor = _coll().find(q).sort("createdAt", -1).limit(limit)
    return [serialize_job(d) for d in cursor]


def requeue_blocked(user_id: str) -> int:
    """
    Flip a user's blocked jobs back to queued and re-enqueue them. Called
    when their plan changes (e.g. they subscribe). Returns count requeued.
    """
    rows = list(_coll().find({"userId": user_id, "status": "blocked"}, {"_id": 1}))
    n = 0
    for r in rows:
        jid = str(r["_id"])
        update_job(jid, status="queued", progress=0, message="Re-queued after upgrade")
        enqueue(jid, user_id)
        n += 1
    return n


def create_blocked_job(
    *,
    user_id: str,
    tool: str,
    params: dict[str, Any],
    reason: str,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
) -> str:
    """
    Same as create_job but starts in 'blocked' state. Used when the user
    submits more work than their free tier allows — we accept the upload
    so they don't have to re-upload after subscribing.
    """
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "userId": user_id,
        "tool": tool,
        "params": params,
        "status": "blocked",
        "progress": 0,
        "message": reason,
        "outputPath": None,
        "outputContentType": None,
        "errorDetail": None,
        "createdAt": now,
        "updatedAt": now,
    }
    if project_id:
        doc["projectId"] = project_id
    if project_name:
        doc["projectName"] = project_name
    res = _coll().insert_one(doc)
    return str(res.inserted_id)


# Helper used by handlers to report progress without importing too much.
def progress(job_id: str, *, pct: int, message: Optional[str] = None) -> None:
    update_job(job_id, progress=max(0, min(100, pct)), message=message)


# Re-export time for handlers that want to do real work.
__all__ = [
    "create_job",
    "get_job",
    "update_job",
    "serialize_job",
    "register_handler",
    "enqueue",
    "start_worker_thread",
    "progress",
    "time",
]
