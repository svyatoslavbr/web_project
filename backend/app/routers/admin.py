import json

from fastapi import APIRouter, Depends
from rq import Worker
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_admin_user, get_db
from app.models import Task, User
from app.taskq import redis_conn, task_queue

router = APIRouter(prefix="/admin", tags=["admin"])

CONTAINER_STATS_KEY = "container_stats"


def read_container_stats() -> list[dict]:
    raw = redis_conn.get(CONTAINER_STATS_KEY)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except ValueError:
        return []


def list_workers() -> list[dict]:
    return sorted(
        (
            {
                "name": worker.name,
                "hostname": worker.hostname,
                "state": worker.get_state(),
                "current_job": worker.get_current_job_id(),
            }
            for worker in Worker.all(connection=redis_conn, queue=task_queue)
        ),
        key=lambda item: item["hostname"] or "",
    )


@router.get("/overview")
def overview(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    by_status = dict(db.execute(select(Task.status, func.count()).group_by(Task.status)).all())
    return {
        "containers": read_container_stats(),
        "queue": {"queued": by_status.get("queued", 0), "running": by_status.get("running", 0)},
        "workers": list_workers(),
        "users_total": db.scalar(select(func.count()).select_from(User)),
        "tasks_by_status": by_status,
    }
