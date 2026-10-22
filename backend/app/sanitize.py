"""Content sanitization — strips HTML and dangerous patterns from user input.

All user-submitted text passes through sanitize_content() before being stored.
This is defense-in-depth: the frontend renders markdown via react-markdown which
escapes raw HTML, but sanitizing server-side protects against:
- Different clients rendering content differently (Telegram notifications)
- Raw HTML stored in DB being rendered unsafely by future clients
- Markdown injection via HTML entities bypassing markdown parsers

HTML stripping uses the maintained, allowlist-based ``nh3`` (Ammonia) sanitizer
when available — strictly safer than a regex denylist, which can be bypassed by
malformed tags. If ``nh3`` is not installed we fall back to the regex stripper so
the app still degrades safely rather than failing to import.

URL-scheme neutralization (javascript:/data:) is always applied with regex
because those attacks live in *markdown* link targets (e.g. ``[x](javascript:…)``),
which are not HTML tags and so are invisible to an HTML sanitizer.
"""
import html
import json
import re

try:
    import nh3
    _HAS_NH3 = True
except Exception:  # pragma: no cover - import guard
    _HAS_NH3 = False

_HTML_TAG_RE = re.compile(r"<[^>]*>", re.DOTALL)
_SCRIPT_LIKE_RE = re.compile(
    r"</?(script|iframe|object|embed|form|applet|meta|link|style|base|svg|math)[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_JAVASCRIPT_URL_RE = re.compile(r"javascript\s*:", re.IGNORECASE)
_DATA_URL_RE = re.compile(r"data\s*:\s*(text/html|image/svg\+xml|application/xml|image/svg)", re.IGNORECASE)
_EVENT_HANDLER_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)

MAX_CONTENT_LENGTH = 50000


def _strip_html(text: str) -> str:
    if _HAS_NH3:
        # Allow no tags/attributes -> all HTML markup is removed, inner text kept.
        return nh3.clean(text, tags=set(), attributes={}, strip_comments=True)
    # Regex fallback (defense-in-depth ordering: known dangerous tags, then all tags).
    text = _SCRIPT_LIKE_RE.sub("", text)
    text = _EVENT_HANDLER_RE.sub("data-blocked-", text)
    text = _HTML_TAG_RE.sub("", text)
    return text


def sanitize_content(text: str | None) -> str | None:
    """Strip HTML tags and dangerous patterns from user content."""
    if text is None:
        return None

    if not isinstance(text, str):
        return text

    if len(text) > MAX_CONTENT_LENGTH:
        text = text[:MAX_CONTENT_LENGTH]

    # Strip HTML markup (allowlist sanitizer preferred).
    text = _strip_html(text)

    # nh3/ammonia HTML-escapes the remaining text (& -> &amp;, < -> &lt;) to make
    # it safe *HTML*. Our content is rendered as plain text / markdown (never
    # injected as raw HTML), so decode those entities back to characters — i.e.
    # a title "Tom & Jerry" must stay "Tom & Jerry", not become "Tom &amp; Jerry".
    if _HAS_NH3:
        text = html.unescape(text)

    # Neutralize dangerous URL schemes (e.g. in markdown link targets). Done
    # AFTER decoding so an entity-encoded scheme can't slip past the check.
    text = _JAVASCRIPT_URL_RE.sub("blocked:", text)
    text = _DATA_URL_RE.sub("blocked:", text)

    return text


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def sanitize_profile_theme(value) -> str | None:
    """Validate the premium `profile_theme` JSON before storing it.

    The theme's `name_color`/`avatar_border` are interpolated into inline CSS on
    the client, so we hard-restrict to: an allowlist of keys, hex-only colors, and
    a boolean glow. Anything else (extra keys, non-hex/oversized values, non-JSON)
    is dropped. Returns a compact JSON string with only valid entries, or None.
    """
    if not value:
        return None
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except (ValueError, TypeError):
            return None
    elif isinstance(value, dict):
        data = value
    else:
        return None
    if not isinstance(data, dict):
        return None

    out: dict = {}
    for key in ("name_color", "avatar_border"):
        v = data.get(key)
        if isinstance(v, str) and _HEX_COLOR_RE.match(v.strip()):
            out[key] = v.strip()
    if data.get("avatar_glow") is True:
        out["avatar_glow"] = True

    return json.dumps(out) if out else None
