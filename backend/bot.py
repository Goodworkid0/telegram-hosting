"""Telegram Bot — file-hosting ingest + Mini App launcher"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from backend directory
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, MenuButtonWebApp, BotCommand,
)
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
WEBAPP_APP_URL = f"{WEBAPP_URL}/app"
APP_NAME = os.getenv("APP_NAME", "Hosting")

# Channels the bot mirrors dropped files into. RETRIEVAL is the durable source
# used to (re)generate file_ids; BACKUP is a redundant archive copy. Both must
# have the bot as an admin. File-sharing ingestion is disabled if RETRIEVAL is
# unset. IDs look like -1001234567890.
RETRIEVAL_CHANNEL_ID = os.getenv("FILES_RETRIEVAL_CHANNEL_ID", "").strip()
BACKUP_CHANNEL_ID = os.getenv("FILES_BACKUP_CHANNEL_ID", "").strip()

# Per-user upload caps (anti-abuse + protects the bot from Telegram flood limits
# on the shared channels). Over-limit drops are refused BEFORE any channel call.
def _int_env(name, default):
    try:
        return max(0, int(os.getenv(name, str(default)) or default))
    except ValueError:
        return default

FILES_MAX_PER_HOUR = _int_env("FILES_MAX_PER_HOUR", 20)
FILES_MAX_PER_DAY = _int_env("FILES_MAX_PER_DAY", 100)

if not TOKEN:
    logger.error("BOT_TOKEN not set in .env")
    sys.exit(1)
if not WEBAPP_URL:
    logger.error("WEBAPP_URL not set in .env")
    sys.exit(1)

WELCOME_TEXT = f"""Welcome to **{APP_NAME}**! 📁

Telegram-powered file hosting: drop a file here and it's published on the board — no size limits, nothing re-uploaded.

• Drop any file in this chat to share it
• Browse and download from the file board
• Set a price on your files and get paid
• Free tier: limited daily downloads — subscribe for unlimited
• Build reputation on your profile

Tap the button below to open the app."""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — show welcome message with Open App button."""
    user = update.effective_user
    logger.info(f"/start from @{user.username or user.id}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            text="Open App",
            web_app=WebAppInfo(url=WEBAPP_APP_URL),
        )],
        [InlineKeyboardButton(
            text="Browse Files",
            web_app=WebAppInfo(url=f"{WEBAPP_APP_URL}/files"),
        )],
    ])

    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )


def _extract_file(message):
    """Return (kind, file_obj) for a supported media message, or (None, None)."""
    if message.document:
        return "document", message.document
    if message.photo:
        return "photo", message.photo[-1]  # largest size
    if message.video:
        return "video", message.video
    if message.audio:
        return "audio", message.audio
    if message.voice:
        return "voice", message.voice
    return None, None


async def file_drop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ingest a file a user dropped in the bot's DM: mirror to the retrieval +
    backup channels and record it as PENDING for ACP approval. Never downloads
    bytes — only shuffles Telegram file references."""
    message = update.effective_message
    if message is None:
        return
    kind, fobj = _extract_file(message)
    if not fobj:
        return

    if not RETRIEVAL_CHANNEL_ID:
        await message.reply_text("File sharing isn't configured yet. Please try later.")
        logger.warning("File drop received but FILES_RETRIEVAL_CHANNEL_ID is unset")
        return

    # Imported lazily so the bot still boots for /start if the app package or DB
    # is momentarily unavailable.
    from datetime import datetime, timedelta
    from sqlalchemy import select, func
    from app.database import async_session
    from app.models import SharedFile, SharedFileStatus, FileCategory, User

    file_unique_id = fobj.file_unique_id
    file_name = getattr(fobj, "file_name", None) or (message.caption or "").strip()[:120] or f"{kind}_{file_unique_id[:8]}"
    mime_type = getattr(fobj, "mime_type", None)
    file_size = getattr(fobj, "file_size", None)
    caption = (message.caption or "").strip() or None
    uploader_tg_id = str(update.effective_user.id)

    cat_list = []  # [(id, name)] captured inside the session for the suggestion keyboard
    async with async_session() as db:
        # Any registered (non-banned) user may share files.
        uploader = await db.scalar(select(User).where(User.telegram_id == uploader_tg_id))
        if not uploader:
            await message.reply_text("Please open the app and register first, then send the file again.")
            return
        if uploader.is_banned:
            await message.reply_text("Your account is banned — file sharing is unavailable.")
            return

        exists = await db.scalar(select(SharedFile).where(SharedFile.file_unique_id == file_unique_id))
        if exists:
            await message.reply_text("You've already shared that file.")
            return

        # Per-user rate limit — checked BEFORE forwarding so an over-limit user
        # triggers zero channel API calls (only the one reply below).
        now = datetime.utcnow()
        if FILES_MAX_PER_HOUR:
            hourly = await db.scalar(select(func.count(SharedFile.id)).where(
                SharedFile.uploader_tg_id == uploader_tg_id,
                SharedFile.created_at > now - timedelta(hours=1),
            ))
            if (hourly or 0) >= FILES_MAX_PER_HOUR:
                await message.reply_text(
                    f"You've hit the hourly upload limit ({FILES_MAX_PER_HOUR}). Please try again later."
                )
                return
        if FILES_MAX_PER_DAY:
            daily = await db.scalar(select(func.count(SharedFile.id)).where(
                SharedFile.uploader_tg_id == uploader_tg_id,
                SharedFile.created_at > now - timedelta(days=1),
            ))
            if (daily or 0) >= FILES_MAX_PER_DAY:
                await message.reply_text(
                    f"You've hit the daily upload limit ({FILES_MAX_PER_DAY}). Please try again tomorrow."
                )
                return

        # Mirror to the retrieval channel and capture the durable message_id +
        # a channel-scoped file_id (survives the user deleting their DM copy).
        try:
            fwd = await context.bot.forward_message(
                chat_id=RETRIEVAL_CHANNEL_ID,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
        except Exception as e:
            logger.warning("Retrieval-channel forward failed: %s", e)
            await message.reply_text("Couldn't accept the file right now. Please try again.")
            return

        r_kind, r_fobj = _extract_file(fwd)
        retrieval_file_id = r_fobj.file_id if r_fobj else fobj.file_id

        backup_message_id = None
        if BACKUP_CHANNEL_ID:
            try:
                bk = await context.bot.forward_message(
                    chat_id=BACKUP_CHANNEL_ID,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id,
                )
                backup_message_id = bk.message_id
            except Exception as e:
                logger.warning("Backup-channel forward failed (non-fatal): %s", e)

        new_file = SharedFile(
            file_unique_id=file_unique_id,
            file_id=retrieval_file_id,
            kind=kind,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            caption=caption,
            uploader_id=uploader.id,
            uploader_tg_id=uploader_tg_id,
            retrieval_chat_id=str(RETRIEVAL_CHANNEL_ID),
            retrieval_message_id=fwd.message_id,
            backup_chat_id=str(BACKUP_CHANNEL_ID) or None,
            backup_message_id=backup_message_id,
            status=SharedFileStatus.PENDING,
        )
        db.add(new_file)
        await db.flush()          # assign id for the suggestion callback_data
        file_db_id = new_file.id

        # Active categories the uploader can suggest from (captured before the
        # session closes so we can build the keyboard afterwards).
        cats = (await db.execute(
            select(FileCategory).where(FileCategory.is_active == True)
            .order_by(FileCategory.sort_order, FileCategory.name)
        )).scalars().all()
        cat_list = [(c.id, c.name) for c in cats]

        await db.commit()

    # Plain text (no parse_mode): filenames often contain Markdown metacharacters
    # (_, *, `) that would break parsing and raise on reply. Offer a category
    # suggestion via inline buttons (the admin still decides on approval).
    keyboard = None
    if cat_list:
        rows, row = [], []
        for cid, cname in cat_list:
            row.append(InlineKeyboardButton(cname[:32], callback_data=f"catsug:{file_db_id}:{cid}"))
            if len(row) == 2:
                rows.append(row); row = []
        if row:
            rows.append(row)
        rows.append([InlineKeyboardButton("Skip", callback_data=f"catsug:{file_db_id}:0")])
        keyboard = InlineKeyboardMarkup(rows)

    await message.reply_text(
        f"✅ Received \"{file_name}\" — it'll appear on the file board once an admin approves it. "
        "After approval you can set a price on it under My Files in the app."
        + ("\n\nSuggest a category:" if keyboard else ""),
        reply_markup=keyboard,
    )
    logger.info("File drop stored: %s from %s", file_unique_id, uploader_tg_id)


async def category_suggestion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Record the uploader's category suggestion from the inline keyboard."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("catsug:"):
        return
    await query.answer()
    try:
        _, fid, cid = query.data.split(":")
        fid, cid = int(fid), int(cid)
    except (ValueError, AttributeError):
        return

    from sqlalchemy import select
    from app.database import async_session
    from app.models import SharedFile, FileCategory

    label = "No category"
    async with async_session() as db:
        f = await db.get(SharedFile, fid)
        if not f:
            return
        # Only the original uploader may set the suggestion.
        if f.uploader_tg_id != str(query.from_user.id):
            return
        if cid == 0:
            f.suggested_category_id = None
        else:
            cat = await db.get(FileCategory, cid)
            if not cat:
                return
            f.suggested_category_id = cid
            label = cat.name
        await db.commit()

    try:
        await query.edit_message_text(f"✅ Thanks — suggested category: {label}. Awaiting admin approval.")
    except Exception:
        pass


async def set_bot_commands(app: Application) -> None:
    """Set bot command suggestions in the chat input."""
    commands = [
        BotCommand("start", "Open the file board"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot commands set")


async def set_menu_button(app: Application) -> None:
    """Set the Telegram menu button to open the WebApp."""
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=f"Open {APP_NAME}",
                web_app=WebAppInfo(url=WEBAPP_APP_URL),
            )
        )
        logger.info(f"Menu button set to WebApp URL: {WEBAPP_APP_URL}")
    except Exception as e:
        logger.warning(f"Failed to set menu button: {e}")


async def post_init(app: Application) -> None:
    """Called after the app is initialized."""
    await set_bot_commands(app)
    await set_menu_button(app)
    logger.info(f"Bot started. WebApp: {WEBAPP_URL}")


def main() -> None:
    """Start the bot with long polling."""
    builder = Application.builder().token(TOKEN).post_init(post_init)
    # Global API throttle: keeps the bot within Telegram's flood limits and
    # auto-retries on 429 (retry_after) instead of erroring — the main guard
    # against the bot getting flood-waited/suspended when many files arrive.
    try:
        from telegram.ext import AIORateLimiter
        builder = builder.rate_limiter(AIORateLimiter())
    except Exception as e:
        logger.warning("Rate limiter unavailable (%s) — install python-telegram-bot[rate-limiter]", e)
    app = builder.build()

    app.add_handler(CommandHandler("start", start_command))
    # Ingest files dropped into the bot's private chat (documents + media).
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (
            filters.Document.ALL | filters.PHOTO | filters.VIDEO
            | filters.AUDIO | filters.VOICE
        ),
        file_drop_handler,
    ))
    app.add_handler(CallbackQueryHandler(category_suggestion_handler, pattern=r"^catsug:"))

    logger.info("Starting bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
