"""Async OTP service backed by Redis.

Key format : otp:{user_id}
Value      : Redis hash {otp_code: "123456", attempts: "0"}
TTL        : 120 seconds (OTP_TTL_SECONDS)

Verification is atomic via a Lua script: read-compare-delete (or increment
attempts) happens in one Redis round-trip with no interleaving from
concurrent requests.
"""
import logging
import os
import secrets

from app.core.redis_client import OTP_TTL_SECONDS, async_redis_client, otp_key


logger = logging.getLogger(__name__)

MAX_ATTEMPTS: int = 3
_IS_DEV: bool = os.getenv("APP_ENV", "dev").lower() != "production"


_VERIFY_SCRIPT = """
local key  = KEYS[1]
local code = ARGV[1]
local max  = tonumber(ARGV[2])

local data = redis.call('HGETALL', key)
if #data == 0 then return {'expired', '0'} end

local fields = {}
for i = 1, #data, 2 do fields[data[i]] = data[i+1] end

local stored = fields['otp_code'] or ''
if stored == '' then return {'expired', '0'} end

if stored == code then
    redis.call('DEL', key)
    return {'ok', '0'}
end

local att = redis.call('HINCRBY', key, 'attempts', 1)
if att >= max then
    redis.call('DEL', key)
    return {'locked', tostring(att)}
end

return {'invalid', tostring(att)}
"""


async def create_otp(user_id: int) -> str:
    """Generate, persist, and return a 6-digit OTP. Overwrites any existing."""
    code = str(secrets.randbelow(900_000) + 100_000)
    key = otp_key(user_id)
    async with async_redis_client.pipeline(transaction=True) as pipe:
        await pipe.delete(key)
        await pipe.hset(key, mapping={"otp_code": code, "attempts": 0})
        await pipe.expire(key, OTP_TTL_SECONDS)
        await pipe.execute()

    if _IS_DEV:
        logger.info("[DEV] OTP for user_id=%d -> %s  (TTL %ds)", user_id, code, OTP_TTL_SECONDS)
    return code


async def verify_otp(user_id: int, otp_input: str) -> bool:
    """Atomically verify the OTP. Returns True on success, raises ValueError otherwise."""
    result = await async_redis_client.eval(
        _VERIFY_SCRIPT, 1, otp_key(user_id), otp_input, str(MAX_ATTEMPTS),
    )
    status: str = result[0]

    if status == "expired":
        raise ValueError("OTP expired or not found.")
    if status == "ok":
        return True
    if status == "locked":
        raise ValueError("Maximum OTP attempts exceeded. Please log in again.")

    new_attempts = int(result[1])
    remaining = MAX_ATTEMPTS - new_attempts
    raise ValueError(
        f"Invalid OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
    )


async def delete_otp(user_id: int) -> None:
    await async_redis_client.delete(otp_key(user_id))
