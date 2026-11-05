from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db
from app.models import Task, User
from app.schemas import GeneratedIn, LinearSystemIn, TaskCreate, TaskOut
from app.taskq import cancel_key, redis_conn, task_queue

router = APIRouter(prefix="/tasks", tags=["tasks"])

ACTIVE_STATUSES = ("queued", "running")


def count_active(db: Session, user_id: int | None = None) -> int:
    stmt = select(func.count()).select_from(Task).where(Task.status.in_(ACTIVE_STATUSES))
    if user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)
    return db.scalar(stmt)


def get_owned_task(task_id: int, db: Session, user: User) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def check_size(data: TaskCreate) -> None:
    if data.kind == "linear_system":
        if not isinstance(data.data, LinearSystemIn):
            raise HTTPException(422, "Expected matrix and vector")
        if len(data.data.matrix) > settings.max_json_unknowns:
            raise HTTPException(422, f"Too many unknowns for JSON input, max {settings.max_json_unknowns}")
    else:
        if not isinstance(data.data, GeneratedIn):
            raise HTTPException(422, "Expected n and seed")
        if data.data.n > settings.max_unknowns:
            raise HTTPException(422, f"Too many unknowns, max {settings.max_unknowns}")


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_size(data)
    if count_active(db) >= settings.max_queue_size:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Queue is full, try again later",
        )
    if count_active(db, user.id) >= settings.max_active_tasks_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many active tasks",
        )
    task = Task(
        user_id=user.id,
        kind=data.kind,
        params=data.data.model_dump(),
        status="queued",
        progress=0,
        stage="У черзі",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    task_queue.enqueue(
        "app.worker.run_task",
        task.id,
        job_timeout=settings.max_task_seconds + 30,
    )
    return task


@router.get("", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(Task).where(Task.user_id == user.id).order_by(Task.id.desc())
    ).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return get_owned_task(task_id, db, user)


@router.post("/{task_id}/cancel", response_model=TaskOut)
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = get_owned_task(task_id, db, user)
    if task.status == "queued":
        task.status = "cancelled"
        task.stage = "Скасовано"
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
    elif task.status == "running":
        redis_conn.set(cancel_key(task.id), 1, ex=settings.max_task_seconds + 60)
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is already finished",
        )
    db.refresh(task)
    return task
