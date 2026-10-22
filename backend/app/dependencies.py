"""Shared FastAPI dependencies"""
import os
from slowapi import Limiter
from slowapi.util import get_remote_address

REDIS_URL = os.getenv("REDIS_URL", "").strip()

# Number of trusted reverse proxies in front of the app (e.g. 1 for a single
# nginx, 2 for Cloudflare -> nginx). The rate-limit key and audit-log client IP
# are derived from X-Forwarded-For ONLY this many hops deep; everything the client
# itself injected to the left is ignored. Default 0 = do NOT trust XFF at all and
# use the socket peer, so a misconfigured deployment can't be spoofed into giving
# every attacker a fresh rate-limit bucket via a forged X-Forwarded-For header.
TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))

# Default cap for endpoints without an explicit @limiter.limit decorator. Applied
# globally once SlowAPIMiddleware is installed. Generous enough for a normal SPA
# session, low enough to blunt scraping / resource-exhaustion. Tunable via env.
DEFAULT_RATE_LIMIT = os.getenv("DEFAULT_RATE_LIMIT", "300/minute")


def real_client_ip(request) -> str:
    """Best-effort real client IP, resistant to X-Forwarded-For spoofing.

    With TRUSTED_PROXY_COUNT proxies, the real client is the entry our outermost
    trusted proxy appended — counted from the RIGHT of X-Forwarded-For. Entries to
    the left are client-supplied and untrusted. With no trusted proxies we use the
    socket peer (request.client.host), which the client cannot forge.
    """
    if TRUSTED_PROXY_COUNT > 0:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if len(parts) >= TRUSTED_PROXY_COUNT:
                return parts[-TRUSTED_PROXY_COUNT]
    return get_remote_address(request)


_limiter_kwargs = dict(key_func=real_client_ip, default_limits=[DEFAULT_RATE_LIMIT])
if REDIS_URL:
    _limiter_kwargs["storage_uri"] = REDIS_URL

limiter = Limiter(**_limiter_kwargs)
