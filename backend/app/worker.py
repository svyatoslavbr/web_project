from datetime import datetime, timezone

import numpy as np

from app.config import settings
from app.db import SessionLocal
from app.models import Task
from app.solvers.linear import Cancelled, TimeLimitExceeded, solve_linear_system
from app.solvers.sparse import generate_system, solve_sparse
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
            if task.kind == "linear_system":
                x = solve_linear_system(
                    task.params["matrix"],
                    task.params["vector"],
                    report,
                    should_cancel,
                    settings.max_task_seconds,
                )
                task.result = {"x": x}
            else:
                report(0, "Генерація системи")
                a, b, x_true = generate_system(task.params["n"], task.params["seed"])
                x, iterations = solve_sparse(
                    a, b, report, should_cancel, settings.max_task_seconds
                )
                report(97, "Перевірка розв'язку")
                task.result = {
                    "max_error": float(np.max(np.abs(x - x_true))),
                    "iterations": iterations,
                    "x_head": x[:10].tolist(),
                }
            task.status = "done"
            task.stage = "Готово"
            task.progress = 100
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
