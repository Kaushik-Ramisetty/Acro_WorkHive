"""Redis client (sync + async) + OTP key/TTL helpers.

Sync client is used by service-layer code that runs inside FastAPI's thread
pool; async client is used by standalone async helpers in otp_service.py.
Both share the same REDIS_URL from settings.
"""
import redis
import redis.asyncio as aioredis

from app.core.config import settings


REDIS_URL: str = settings.REDIS_URL

OTP_TTL_SECONDS: int = settings.OTP_TTL_SECONDS or 120
_OTP_PREFIX: str = "otp"


def otp_key(user_id: int) -> str:
    return f"{_OTP_PREFIX}:{user_id}"


# Sync client — used by service-layer code in a thread pool.
redis_client: redis.Redis = redis.from_url(REDIS_URL, decode_responses=True)

# Async client — used by standalone async helpers (otp_service.py).
async_redis_client: aioredis.Redis = aioredis.from_url(REDIS_URL, decode_responses=True)


async def ping_redis() -> None:
    """Verify Redis is reachable. Raises ConnectionError on failure."""
    await async_redis_client.ping()


async def close_redis() -> None:
    redis_client.close()
    await async_redis_client.aclose()
