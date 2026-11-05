from redis import Redis
from rq import Queue

from app.config import settings

redis_conn = Redis.from_url(settings.redis_url)
task_queue = Queue("tasks", connection=redis_conn)


def cancel_key(task_id: int) -> str:
    return f"cancel:{task_id}"
