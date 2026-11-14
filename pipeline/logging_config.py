"""Small, dependency-free execution tracing shared by every pipeline stage."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

LOGGER = logging.getLogger("terps.pipeline")
RUN_ID = ContextVar("pipeline_run_id", default=None)
STAGE = ContextVar("pipeline_stage", default="execution")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname, "run_id": getattr(record, "run_id", "unscoped"),
            "stage": getattr(record, "stage", "execution"),
            "event": getattr(record, "event", record.getMessage()),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, allow_nan=False, default=lambda _: "<unserializable>")
        except (TypeError, ValueError):
            # Keep the original level/event; malformed diagnostics never imply success.
            payload = {key: payload[key] for key in ("timestamp", "level", "run_id", "stage", "event")}
            payload["logging_error"] = "invalid_structured_fields"
            return json.dumps(payload)


def configure_logging(level=None, jsonl=None, human=False):
    level = (level or os.getenv("PIPELINE_LOG_LEVEL", "INFO")).upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("Invalid logging level")
    for handler in list(LOGGER.handlers):
        LOGGER.removeHandler(handler)
        handler.close()
    LOGGER.setLevel(level)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(run_id)s %(stage)s %(event)s %(fields)s") if human else JsonFormatter())
    LOGGER.addHandler(console)
    jsonl = jsonl or os.getenv("PIPELINE_LOG_FILE")
    if jsonl:
        path = Path(jsonl)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        LOGGER.addHandler(file_handler)


def fingerprint(config):
    """Fingerprint configuration without emitting its contents or secrets."""
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()


def event(name, level=logging.INFO, *, exc_info=None, **fields):
    if not LOGGER.handlers:
        configure_logging()
    try:
        LOGGER.log(level, name, extra={"event": name, "run_id": RUN_ID.get() or "unscoped",
                                      "stage": STAGE.get(), "fields": fields}, exc_info=exc_info)
    except Exception:
        # Diagnostics cannot change a computation's result or suppress its exception.
        sys.stderr.write('{"level":"ERROR","event":"logging_failed"}\n')


@contextmanager
def operation(stage, **context):
    run_token = RUN_ID.set(str(uuid4())) if RUN_ID.get() is None else None
    stage_token = STAGE.set(stage)
    started = perf_counter()
    event("operation_started", **context)
    try:
        yield
    except Exception:
        event("operation_failed", logging.ERROR, exc_info=True,
              duration_ms=(perf_counter() - started) * 1000, **context)
        raise
    else:
        event("operation_completed", duration_ms=(perf_counter() - started) * 1000, **context)
    finally:
        STAGE.reset(stage_token)
        if run_token is not None:
            RUN_ID.reset(run_token)


def traced(stage):
    def decorate(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            with operation(stage, operation=function.__name__):
                return function(*args, **kwargs)
        return wrapper
    return decorate
