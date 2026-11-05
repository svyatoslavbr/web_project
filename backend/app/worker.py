from datetime import datetime, timezone

from app.config import settings
from app.db import SessionLocal
from app.models import Task
from app.solvers.linear import Cancelled, TimeLimitExceeded, solve_linear_system
from app.taskq import cancel_key, redis_conn


def run_task(task_id: int) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task is None or task.status != "queued":
            return
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        db.commit()

        last_progress = -1

        def report(progress: int, stage: str) -> None:
            nonlocal last_progress
            if progress == last_progress:
                return
            last_progress = progress
            task.progress = progress
            task.stage = stage
            db.commit()

        def should_cancel() -> bool:
            return redis_conn.exists(cancel_key(task_id)) == 1

        try:
            x = solve_linear_system(
                task.params["matrix"],
                task.params["vector"],
                report,
                should_cancel,
                settings.max_task_seconds,
            )
            task.result = {"x": x}
            task.status = "done"
            task.stage = "Готово"
        except Cancelled:
            task.status = "cancelled"
            task.stage = "Скасовано"
        except TimeLimitExceeded:
            task.status = "failed"
            task.error = "Перевищено ліміт часу"
        except ValueError as exc:
            task.status = "failed"
            task.error = str(exc)

        task.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        redis_conn.delete(cancel_key(task_id))
        db.close()
