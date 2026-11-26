"""
Production AI Agent — Part 6 Final Project
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format every log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
root_logger = logging.getLogger()
root_logger.handlers = [handler]
root_logger.setLevel(logging.INFO)

for uv_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    uv_logger = logging.getLogger(uv_logger_name)
    uv_logger.handlers = [handler]
    uv_logger.propagate = False

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", extra={"extra_fields": {"event": "startup"}})
    yield
    logger.info("shutdown", extra={"extra_fields": {"event": "shutdown"}})
    try:
        r.close()
    except Exception:
        pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request",
        extra={
            "extra_fields": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_error",
        extra={"extra_fields": {"event": "error", "path": request.url.path}},
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/health")
def health():
    """Liveness probe — always returns 200 while process is running."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe — returns 200 when Redis is reachable, else 503."""
    if not redis_healthy():
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "redis": "unavailable"},
        )
    return {"status": "ready", "redis": "ok"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question) // 4)
    output_tokens = max(1, len(answer) // 4)
    cost_usd = record_cost(input_tokens, output_tokens)
    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": cost_usd,
    }
