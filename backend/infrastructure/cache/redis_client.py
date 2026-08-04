from __future__ import annotations

import redis

from backend.core.config import settings


def get_redis_client():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
