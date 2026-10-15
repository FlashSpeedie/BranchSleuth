import logging
import sys
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class SanitizingFilter(logging.Filter):
    SENSITIVE_HINTS = ("password", "token", "secret", "authorization", "api_key", "database_url", "postgres://", "npg_")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        low = msg.lower()
        return not any(h in low for h in self.SENSITIVE_HINTS)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SanitizingFilter())
    handler.setFormatter(
        logging.Formatter(
            '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","request_id":"'
            + "%(request_id)s"
            + '","message":"%(message)s"}'
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "docker", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


old_factory = logging.getLogRecordFactory()


def record_factory(*args, **kwargs):
    record = old_factory(*args, **kwargs)
    record.request_id = request_id_ctx.get()
    return record


logging.setLogRecordFactory(record_factory)
