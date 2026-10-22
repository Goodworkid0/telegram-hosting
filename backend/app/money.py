"""Decimal money helpers.

All USD money is a Decimal quantized to cents. Server-side math is exact Decimal;
the HTTP API still speaks dollars as JSON numbers — FastAPI's encoder converts
Decimal -> float on output and Pydantic coerces Decimal <-> float for float
schema fields, so the wire contract is unchanged. Convert *incoming* amounts with
to_money() before doing any math or persisting.

Crypto amounts (BTC/XMR pay amounts, payout amounts) are NOT cents — they keep
their own precision and stay floats at the external-rate boundary.
"""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def to_money(value) -> Decimal:
    """Coerce int/float/str/Decimal/None to a cents-quantized Decimal (half-up).

    Floats are stringified first to avoid binary-float repr noise
    (e.g. 0.1 + 0.2). None -> 0.00.
    """
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, float):
        d = Decimal(str(value))
    else:  # int / str
        d = Decimal(value)
    if not d.is_finite():  # reject NaN / sNaN / Infinity (would poison ledger comparisons)
        raise ValueError("amount must be a finite number")
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def apply_percent(amount, percent) -> Decimal:
    """Return amount * percent%, quantized to cents (half-up).

    `percent` is a human percentage (e.g. 3 means 3%). Accepts float/Decimal.
    """
    amt = to_money(amount)
    pct = percent if isinstance(percent, Decimal) else Decimal(str(percent or 0))
    return (amt * pct / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
