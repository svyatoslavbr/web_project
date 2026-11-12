import json
import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import docker
from redis import Redis
from rq import Queue, Worker

PROJECT = os.environ.get("COMPOSE_PROJECT_NAME", "web_project")
SERVICE = "worker"
AUTOSCALED_LABEL = "web_project.autoscaled"
MIN_WORKERS = int(os.environ.get("MIN_WORKERS", "1"))
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))
TASKS_PER_WORKER = int(os.environ.get("TASKS_PER_WORKER", "2"))
SCALE_DOWN_IDLE_SECONDS = int(os.environ.get("SCALE_DOWN_IDLE_SECONDS", "60"))
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "5"))
SCALE_COOLDOWN_SECONDS = int(os.environ.get("SCALE_COOLDOWN_SECONDS", "15"))
STOP_TIMEOUT_SECONDS = int(os.environ.get("WORKER_STOP_TIMEOUT_SECONDS", "150"))
CONTAINER_STATS_KEY = "container_stats"
CONTAINER_STATS_TTL_SECONDS = 30

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
log = logging.getLogger("autoscaler")

client = docker.from_env()
redis_conn = Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
queue = Queue("tasks", connection=redis_conn)


def base_workers():
    containers = client.containers.list(
        filters={
            "label": [f"com.docker.compose.project={PROJECT}", f"com.docker.compose.service={SERVICE}"],
            "status": "running",
        }
    )
    return [c for c in containers if AUTOSCALED_LABEL not in c.labels]


def extra_workers(all_states=False):
    return client.containers.list(
        all=all_states,
        filters={"label": [f"{AUTOSCALED_LABEL}={PROJECT}"]},
    )


def next_number(extras):
    used = {int(c.labels.get("web_project.worker_number", "0")) for c in extras}
    number = 2
    while number in used:
        number += 1
    return number


def start_worker():
    templates = base_workers()
    if not templates:
        log.info("Немає базового worker для шаблону, пропускаю")
        return
    template = templates[0]
    extras = extra_workers(all_states=True)
    number = next_number(extras)
    name = f"{PROJECT}-worker-auto-{number}"
    network = next(iter(template.attrs["NetworkSettings"]["Networks"]))
    container = client.containers.run(
        template.image.id,
        command=template.attrs["Config"]["Cmd"],
        name=name,
        hostname=name,
        environment=template.attrs["Config"]["Env"],
        labels={AUTOSCALED_LABEL: PROJECT, "web_project.worker_number": str(number)},
        network=network,
        stop_signal="SIGTERM",
        detach=True,
    )
    log.info("Запущено %s", container.name)


def idle_hostnames():
    hosts = set()
    for worker in Worker.all(queue=queue):
        if worker.get_state() == "idle" and not worker.get_current_job_id():
            hosts.add(worker.hostname)
    return hosts


def stop_idle_worker():
    idle = idle_hostnames()
    candidates = sorted(
        extra_workers(),
        key=lambda c: int(c.labels.get("web_project.worker_number", "0")),
        reverse=True,
    )
    for container in candidates:
        if container.attrs["Config"]["Hostname"] in idle:
            log.info("Зупиняю вільний %s", container.name)
            container.stop(timeout=STOP_TIMEOUT_SECONDS)
            container.remove()
            return True
    log.info("Усі додаткові worker зайняті, зменшення відкладено")
    return False


def remove_dead_extras():
    for container in extra_workers(all_states=True):
        if container.status in ("exited", "dead", "created"):
            log.info("Прибираю зупинений %s", container.name)
            container.remove(force=True)


def cpu_percent(stats):
    cpu = stats.get("cpu_stats", {})
    precpu = stats.get("precpu_stats", {})
    cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - precpu.get("cpu_usage", {}).get("total_usage", 0)
    system_delta = cpu.get("system_cpu_usage", 0) - precpu.get("system_cpu_usage", 0)
    online = cpu.get("online_cpus") or 1
    if cpu_delta <= 0 or system_delta <= 0:
        return 0.0
    return round(cpu_delta / system_delta * online * 100, 1)


def memory_mb(stats):
    memory = stats.get("memory_stats", {})
    usage = memory.get("usage", 0) - memory.get("stats", {}).get("inactive_file", 0)
    return round(max(usage, 0) / 1024 / 1024, 1)


def container_info(container):
    info = {"name": container.name, "status": container.status, "cpu_percent": None, "memory_mb": None}
    if container.status == "running":
        try:
            stats = container.stats(stream=False)
            info["cpu_percent"] = cpu_percent(stats)
            info["memory_mb"] = memory_mb(stats)
        except docker.errors.APIError:
            pass
    return info


def publish_container_stats():
    containers = client.containers.list(
        all=True, filters={"label": f"com.docker.compose.project={PROJECT}"}
    )
    with ThreadPoolExecutor(max_workers=max(1, len(containers))) as pool:
        result = sorted(pool.map(container_info, containers), key=lambda item: item["name"])
    redis_conn.set(CONTAINER_STATS_KEY, json.dumps(result), ex=CONTAINER_STATS_TTL_SECONDS)


def shutdown(*_):
    for container in extra_workers(all_states=True):
        log.info("Завершення: зупиняю %s", container.name)
        try:
            container.stop(timeout=STOP_TIMEOUT_SECONDS)
            container.remove()
        except docker.errors.APIError:
            pass
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    log.info(
        "Автоскейлер запущено: min=%s max=%s задач на worker=%s простій=%s с перевірка=%s с пауза=%s с",
        MIN_WORKERS, MAX_WORKERS, TASKS_PER_WORKER, SCALE_DOWN_IDLE_SECONDS, CHECK_INTERVAL_SECONDS, SCALE_COOLDOWN_SECONDS,
    )
    last_change = 0.0
    idle_since = None
    while True:
        try:
            remove_dead_extras()
            queued = queue.count
            workers = len(base_workers()) + len(extra_workers())
            now = time.monotonic()
            idle_since = (idle_since or now) if queued == 0 else None
            cooled_down = now - last_change >= SCALE_COOLDOWN_SECONDS
            if workers < MIN_WORKERS and cooled_down:
                log.info("Черга %s, worker %s: менше мінімуму, додаю", queued, workers)
                start_worker()
                last_change = now
            elif queued > workers * TASKS_PER_WORKER and workers < MAX_WORKERS and cooled_down:
                log.info("Черга %s, worker %s: додаю ще одного", queued, workers)
                start_worker()
                last_change = now
            elif (
                idle_since is not None
                and now - idle_since >= SCALE_DOWN_IDLE_SECONDS
                and workers > MIN_WORKERS
                and cooled_down
                and extra_workers()
            ):
                log.info("Черга порожня %s с, worker %s: зменшую", int(now - idle_since), workers)
                if stop_idle_worker():
                    last_change = now
        except Exception as exc:
            log.info("Помилка автоскейлера: %s", exc)
        try:
            publish_container_stats()
        except Exception as exc:
            log.info("Помилка збору статистики контейнерів: %s", exc)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
