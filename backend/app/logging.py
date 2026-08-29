"""structlog JSON logging with a secret-redaction processor and correlation id."""
from __future__ import annotations

import logging
import re
from contextvars import ContextVar

import structlog

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{12,}|gsk_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._\-]+)")


def _redact(_, __, event_dict: dict) -> dict:
    for k, v in list(event_dict.items()):
        if isinstance(v, str):
            event_dict[k] = _SECRET_RE.sub("«redacted»", v)
    return event_dict


def _add_correlation(_, __, event_dict: dict) -> dict:
    event_dict.setdefault("correlation_id", correlation_id.get())
    return event_dict


def configure() -> None:
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_correlation,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()
