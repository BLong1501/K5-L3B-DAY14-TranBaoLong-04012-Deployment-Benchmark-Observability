"""
Rate limiting (tiêu chí 7) — Sliding window lưu trong Redis.
"""
import time
import uuid
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r


def check_rate_limit(key: str) -> None:
    """Kiểm tra rate limit theo API key; vượt ngưỡng -> HTTP 429."""
    limit = settings.rate_limit_per_minute
    window_seconds = 60
    now = time.time()
    window_start = now - window_seconds
    redis_key = f"rate_limit:{key}"

    pipe = r.pipeline()
    pipe.zremrangebyscore(redis_key, 0, window_start)
    pipe.zcard(redis_key)
    _, current_count = pipe.execute()

    if current_count >= limit:
        oldest = r.zrange(redis_key, 0, 0, withscores=True)
        retry_after = int(oldest[0][1] + window_seconds - now) + 1 if oldest else window_seconds
        retry_after = max(1, retry_after)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": limit,
                "window_seconds": window_seconds,
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    member = f"{now}:{uuid.uuid4().hex}"
    pipe = r.pipeline()
    pipe.zadd(redis_key, {member: now})
    pipe.expire(redis_key, window_seconds)
    pipe.execute()
