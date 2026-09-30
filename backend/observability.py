from contextvars import ContextVar

REQUEST_ID: ContextVar[str | None] = ContextVar("agrisathi_request_id", default=None)
