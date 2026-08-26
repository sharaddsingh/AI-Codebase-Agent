"""Structured JSON logging with secret redaction.

Logs are emitted as one JSON object per line (easy to ship to any log system).
A filter scrubs anything that looks like a secret (API keys, bearer tokens,
``key=value`` pairs for sensitive names) from every log record's message and
arguments, so credentials never land in logs even if accidentally passed.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

# Patterns that indicate a secret value we must never log verbatim.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),                     # OpenAI / Anthropic sk- keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"),                 # GitHub tokens
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),        # bearer tokens
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[=:]\s*"
        r"['\"]?([^\s'\"]{4,})"
    ),
]

_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 2:
            out = pat.sub(lambda m: m.group(0).replace(m.group(2), _REDACTED), out)
        else:
            out = pat.sub(_REDACTED, out)
    return out


class _RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: _redact_any(v) for k, v in record.args.items()}
                else:
                    record.args = tuple(_redact_any(a) for a in record.args)
        except Exception:  # noqa: BLE001, S110 - logging must never raise; swallow deliberately
            pass
        return True


def _redact_any(value: Any) -> Any:
    return redact(value) if isinstance(value, str) else value


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach any structured extras passed via logger.info(..., extra={"extra": {...}}).
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            payload["data"] = {k: _redact_any(v) for k, v in extra.items()}
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    # Replace handlers so we don't double-log under uvicorn reloads.
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_RedactionFilter())
    root.addHandler(handler)
    # Quiet noisy access logs a touch; keep warnings+.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
