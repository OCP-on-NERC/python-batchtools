from datetime import datetime, timezone
from .helpers import is_on_project

import os
import shutil
import openshift_client as oc

from prometheus_client import (
    CollectorRegistry,
    Histogram,
    Counter,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    pushadd_to_gateway,
)

LONG_JOB_BUCKETS = (1, 2, 5, 10, 20, 30, 60, 120, 180, 300, 600, 900, float("inf"))

PUSHGATEWAY_ADDR = os.getenv("PUSHGATEWAY_ADDR", "pushgateway.ope-test.svc:9091")


def detect_instance() -> str:
    if shutil.which("oc") is None:
        return "devpod"
    try:
        return oc.get_project_name() if is_on_project() else "devpod"
    except Exception:
        return "devpod"


PROMETHEUS_INSTANCE = os.getenv("PROMETHEUS_INSTANCE") or detect_instance()

registry = CollectorRegistry()

BATCH_DURATION = Histogram(
    "batch_duration_seconds",
    "Runtime of batch job (seconds)",
    ["job_name", "gpu", "queue", "result", "instance"],
    registry=registry,
    buckets=LONG_JOB_BUCKETS,
)

BATCH_DURATION_TOTAL = Counter(
    "batch_duration_total_seconds",
    "Total runtime accumulated across all jobs (sum of durations)",
    ["job_name", "gpu", "queue", "result", "instance"],
    registry=registry,
)

BATCH_RUNS = Counter(
    "batch_runs_total",
    "Number of batch runs by result",
    ["job_name", "gpu", "queue", "result", "instance"],
    registry=registry,
)

IN_PROGRESS = Gauge(
    "batch_in_progress",
    "Currently running batch jobs",
    ["job_name", "gpu", "queue", "result", "instance"],
    registry=registry,
)

QUEUE_WAIT = Histogram(
    "batch_queue_wait_seconds",
    "Time from job submission until pod enters Running ...",
    ["job_name", "gpu", "queue", "result", "instance"],
    registry=registry,
    buckets=LONG_JOB_BUCKETS,
)

QUEUE_WAIT_COUNT = Counter(
    "batch_queue_wait_total_seconds",
    "Total accumulated queue wait time across jobs (sum of durations)",
    ["job_name", "gpu", "queue", "result", "instance"],
    registry=registry,
)

TOTAL_WALL = Histogram(
    "batch_total_wall_seconds",
    "End-to-end time from job submission until terminal phase ...",
    ["job_name", "gpu", "queue", "result", "instance"],
    registry=registry,
    buckets=LONG_JOB_BUCKETS,
)

TOTAL_WALL_COUNT = Counter(
    "batch_total_wall_total_seconds",
    "Total accumulated wall time across jobs (sum of durations)",
    ["job_name", "gpu", "queue", "result", "instance"],
    registry=registry,
)


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_batch_observation(*, labels: dict, elapsed_sec: float, result: str) -> None:
    """
    Observe a completed batch run and update counters/histograms.
    """
    lb = dict(labels)
    lb["result"] = result

    # Execution time
    BATCH_DURATION.labels(**lb).observe(elapsed_sec)
    BATCH_DURATION_TOTAL.labels(**lb).inc(elapsed_sec)
    BATCH_RUNS.labels(**lb).inc()


def record_queue_observation(*, labels: dict, elapsed_sec: float, result: str) -> None:
    """Record queue wait metrics"""
    lb = dict(labels)
    lb["result"] = result
    QUEUE_WAIT.labels(**lb).observe(elapsed_sec)
    QUEUE_WAIT_COUNT.labels(**lb).inc(elapsed_sec)


def record_wall_observation(*, labels: dict, elapsed_sec: float, result: str) -> None:
    """Record total wall time metrics"""
    lb = dict(labels)
    lb["result"] = result
    TOTAL_WALL.labels(**lb).observe(elapsed_sec)
    TOTAL_WALL_COUNT.labels(**lb).inc(elapsed_sec)


def set_in_progress(*, labels: dict, result: str, inc: bool) -> None:
    lb = dict(labels)
    lb["result"] = result
    if inc:
        IN_PROGRESS.labels(**lb).inc()
    else:
        IN_PROGRESS.labels(**lb).dec()


def generate_metrics_text() -> tuple[str, str]:
    """Return (body, content_type) for the current registry."""
    payload = generate_latest(registry)
    return payload.decode("utf-8"), CONTENT_TYPE_LATEST


def push_registry_text(grouping_key: dict[str, str] | None = None) -> None:
    if not PUSHGATEWAY_ADDR:
        body, _ = generate_metrics_text()
        print("PROM: PUSHGATEWAY_ADDR not set; below is the metrics payload:\n")
        print(body)
        return
    try:
        pushadd_to_gateway(
            PUSHGATEWAY_ADDR,
            job="batchtools",
            registry=registry,
            grouping_key=grouping_key or {},
        )
        print(f"PROM: metrics pushed to pushgateway={PUSHGATEWAY_ADDR}")
    except Exception as e:
        print(f"PROM: failed to push metrics to pushgateway {PUSHGATEWAY_ADDR}: {e}")
