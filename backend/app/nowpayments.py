"""NOWPayments API helpers: live coin list, display metadata, per-coin minimums.

All network calls are wrapped in short-lived in-process caches and fail soft: on
any upstream error we return a safe fallback (``None`` or the legacy coin set) so
deposits are never blocked by a flaky NOWPayments response. The API key stays
server-side — the frontend only ever sees the resolved/curated coin list.
"""
import os
import time
import logging
import httpx

logger = logging.getLogger(__name__)

NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY", "")
NOWPAYMENTS_BASE_URL = os.getenv("NOWPAYMENTS_BASE_URL", "https://api.nowpayments.io/v1")

# Legacy hardcoded set — used as a fallback when the account's coin list cannot
# be fetched and the admin has not curated their own selection.
DEFAULT_COINS = ["btc", "ltc", "eth", "xmr"]

# Display metadata for common tickers. Anything not listed still renders, just
# with a derived (uppercased ticker) name/network.
COIN_META = {
    "btc":       {"name": "Bitcoin",      "network": "Bitcoin"},
    "ltc":       {"name": "Litecoin",     "network": "Litecoin"},
    "eth":       {"name": "Ethereum",     "network": "ERC-20"},
    "xmr":       {"name": "Monero",       "network": "Monero"},
    "usdttrc20": {"name": "Tether USD",   "network": "TRC-20"},
    "usdterc20": {"name": "Tether USD",   "network": "ERC-20"},
    "usdtsol":   {"name": "Tether USD",   "network": "Solana"},
    "usdtbsc":   {"name": "Tether USD",   "network": "BSC"},
    "usdcerc20": {"name": "USD Coin",     "network": "ERC-20"},
    "usdcsol":   {"name": "USD Coin",     "network": "Solana"},
    "sol":       {"name": "Solana",       "network": "Solana"},
    "trx":       {"name": "Tron",         "network": "Tron"},
    "bnbbsc":    {"name": "BNB",          "network": "BSC"},
    "doge":      {"name": "Dogecoin",     "network": "Dogecoin"},
    "ton":       {"name": "Toncoin",      "network": "TON"},
    "dash":      {"name": "Dash",         "network": "Dash"},
    "bch":       {"name": "Bitcoin Cash", "network": "Bitcoin Cash"},
    "xrp":       {"name": "XRP",          "network": "XRP"},
    "ada":       {"name": "Cardano",      "network": "Cardano"},
    "matic":     {"name": "Polygon",      "network": "Polygon"},
    "pol":       {"name": "Polygon",      "network": "Polygon"},
}

_TTL = 600  # seconds — coins/minimums change rarely
_cache: dict = {}  # key -> (expires_at, value)


def _cache_get(key):
    entry = _cache.get(key)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def _cache_set(key, value, ttl=_TTL):
    _cache[key] = (time.time() + ttl, value)


# Common NOWPayments network suffixes, longest-first, stripped to derive a clean
# ticker symbol (e.g. "usdttrc20" -> "USDT").
_NETWORK_SUFFIXES = ("trc20", "erc20", "bep20", "arc20", "bsc", "sol", "matic")


def _derive_symbol(code: str) -> str:
    for suffix in _NETWORK_SUFFIXES:
        if code.endswith(suffix) and len(code) > len(suffix):
            return code[: -len(suffix)].upper()
    return code.upper()


def coin_display(code: str) -> dict:
    """Return display metadata ({currency, symbol, name, network}) for a ticker."""
    code = code.lower()
    meta = COIN_META.get(code)
    if meta:
        return {
            "currency": code,
            "symbol": _derive_symbol(code),
            "name": meta["name"],
            "network": meta["network"],
        }
    return {
        "currency": code,
        "symbol": _derive_symbol(code),
        "name": _derive_symbol(code),
        "network": code.upper(),
    }


def resolve_enabled(curated_csv: str | None, available: list | None) -> list:
    """Resolve the deposit coin list shown to users.

    ``curated_csv`` is the admin's saved selection (comma-separated tickers).
    ``available`` is the live account coin list, or ``None`` if it couldn't be
    fetched. The result is the curated list filtered to coins still available on
    the account; if the curated list is empty we fall back to ``DEFAULT_COINS``,
    and if availability is unknown we trust the curated list as-is.
    """
    curated = [c.strip().lower() for c in (curated_csv or "").split(",") if c.strip()]
    if not curated:
        curated = list(DEFAULT_COINS)
    if available is None:
        return curated
    avail = set(available)
    filtered = [c for c in curated if c in avail]
    return filtered or curated


async def fetch_available_coins():
    """Coins enabled on THIS NOWPayments account (dashboard selection).

    Returns a list of lowercase tickers, or ``None`` if the list cannot be
    determined (no API key / upstream error) so callers can decide how to fall
    back rather than silently over-filtering.
    """
    cached = _cache_get("available")
    if cached is not None:
        return cached
    if not NOWPAYMENTS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{NOWPAYMENTS_BASE_URL}/merchant/coins",
                headers={"x-api-key": NOWPAYMENTS_API_KEY},
            )
        resp.raise_for_status()
        data = resp.json()
        coins = [c.lower() for c in (data.get("selectedCurrencies") or [])]
        if coins:
            _cache_set("available", coins)
            return coins
    except Exception as e:  # noqa: BLE001 — fail soft, never block deposits
        logger.warning("nowpayments.fetch_available_coins failed: %s", e)
    return None


async def fetch_min_usd(coin: str):
    """Minimum payment amount for ``coin`` expressed in USD, or ``None``.

    Uses NOWPayments' ``/min-amount`` with ``fiat_equivalent=usd``. Per-coin
    minimums are driven by network fees and matter a lot once cheap-to-send and
    expensive-to-send coins coexist (a $10 floor is fine for LTC, far too low for
    an ERC-20 token).
    """
    coin = coin.lower()
    key = f"min:{coin}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    if not NOWPAYMENTS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{NOWPAYMENTS_BASE_URL}/min-amount",
                params={
                    "currency_from": coin,
                    "currency_to": coin,
                    "fiat_equivalent": "usd",
                },
                headers={"x-api-key": NOWPAYMENTS_API_KEY},
            )
        resp.raise_for_status()
        data = resp.json()
        usd = data.get("fiat_equivalent")
        if usd is not None:
            usd = float(usd)
            _cache_set(key, usd)
            return usd
    except Exception as e:  # noqa: BLE001 — fail soft, fall back to global min
        logger.warning("nowpayments.fetch_min_usd(%s) failed: %s", coin, e)
    return None
