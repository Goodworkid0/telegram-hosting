"""Image processing utilities"""
import io
import uuid
from PIL import Image, ImageOps

MAX_DIMENSIONS = (1920, 1920)  # Max width/height
WEBP_QUALITY = 80

# Cap the decoded pixel count to defuse decompression bombs: a tiny, highly
# compressed file (a few hundred KB) can otherwise decode to hundreds of
# megapixels and exhaust memory / tie up a worker thread, even though the
# *compressed* upload passed the byte-size limit. 24 MP is comfortably above our
# 1920x1920 working size. Pillow raises DecompressionBombError above this.
MAX_IMAGE_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class InvalidImageError(ValueError):
    """Raised when uploaded bytes are not a safe, decodable raster image."""

# Map of sniffed raster image type -> canonical file extension. SVG is
# intentionally excluded: it can carry <script> and, served same-origin, becomes
# stored XSS. Only these script-free raster formats are accepted for raw uploads.
_SNIFFED_EXTENSIONS = {
    "png": "png",
    "jpeg": "jpg",
    "gif": "gif",
    "webp": "webp",
}


def sniff_image_type(data: bytes) -> str | None:
    """Return the real image type by inspecting magic bytes, or None if the
    bytes are not a recognized (script-free) raster image. Never trust the
    client-supplied Content-Type or filename for security decisions."""
    if len(data) < 12:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def validated_image_extension(data: bytes) -> str | None:
    """Sniff the image and return its canonical extension (e.g. 'png'), or None
    if the bytes are not an accepted raster image."""
    sniffed = sniff_image_type(data)
    return _SNIFFED_EXTENSIONS.get(sniffed) if sniffed else None


def process_upload(file_data: bytes, filename: str) -> tuple[bytes, str]:
    """Process uploaded image: strip EXIF, resize, convert to WebP.
    Returns (processed_bytes, new_filename).

    Raises InvalidImageError if the bytes are not a recognized, safely decodable
    raster image (wrong/forged type, corrupt, or a decompression bomb)."""
    # Validate by magic bytes BEFORE handing anything to Pillow — never trust the
    # client-supplied Content-Type or filename for this decision.
    if validated_image_extension(file_data) is None:
        raise InvalidImageError("Unsupported or invalid image file")

    try:
        img = Image.open(io.BytesIO(file_data))
    except Exception as e:
        raise InvalidImageError("Could not read image file") from e

    # Reject decompression bombs using the header-declared dimensions, BEFORE the
    # full decode allocates memory. Pillow only raises DecompressionBombError at
    # 2x MAX_IMAGE_PIXELS (and merely warns at the limit), so enforce it here.
    width, height = img.size
    if width * height > MAX_IMAGE_PIXELS:
        raise InvalidImageError("Image dimensions are too large")

    try:
        img.load()  # force the full decode now so any residual bomb is caught here
    except Image.DecompressionBombError as e:
        raise InvalidImageError("Image dimensions are too large") from e
    except Exception as e:
        raise InvalidImageError("Could not read image file") from e

    # Strip EXIF: copy pixel data only, discarding metadata
    if img.mode in ("RGBA", "LA", "P"):
        if img.mode == "P":
            img = img.convert("RGBA")
        # Convert RGBA to RGB on white background (WebP doesn't need alpha for forum images)
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if larger than MAX_DIMENSIONS
    img.thumbnail(MAX_DIMENSIONS, Image.Resampling.LANCZOS)

    # Save as WebP
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=WEBP_QUALITY)
    processed_bytes = buffer.getvalue()

    # Always generate a fresh server-side name. NEVER derive the stored filename
    # from the client-supplied `filename` — that is a path-traversal / arbitrary
    # file-overwrite vector (e.g. "../../../x.jpg"). Output is always WebP.
    new_filename = f"{uuid.uuid4().hex}.webp"

    return processed_bytes, new_filename
