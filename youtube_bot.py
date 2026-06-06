import logging
import os
import re
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ===================== تنظیمات =====================
BOT_TOKEN = "8808033938:AAF9oYXMwKxJBFIzxn4OOviT9fejw-_5b-8"   # <-- توکن ربات خودت رو اینجا بذار
DOWNLOAD_DIR = "./downloads"
MAX_FILE_SIZE_MB = 50  # تلگرام حداکثر 50 MB برای ربات‌های رایگان
# ===================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def is_youtube_url(text: str) -> bool:
    pattern = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
    return bool(re.match(pattern, text.strip()))


def get_video_info(url: str) -> dict | None:
    ydl_opts = {"quiet": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Error getting info: {e}")
        return None


# ===================== هندلرها =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 👋\n"
        "لینک ویدیوی یوتیوب رو برام بفرست تا دانلودش کنم.\n\n"
        "مثال:\nhttps://www.youtube.com/watch?v=..."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 راهنما:\n"
        "1. لینک ویدیوی یوتیوب رو بفرست\n"
        "2. کیفیت مورد نظر رو انتخاب کن\n"
        "3. منتظر دانلود بمون!\n\n"
        "⚠️ حداکثر حجم فایل: 50 مگابایت"
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not is_youtube_url(url):
        await update.message.reply_text("❌ لینک یوتیوب معتبر نیست. یه لینک درست بفرست.")
        return

    msg = await update.message.reply_text("⏳ در حال دریافت اطلاعات ویدیو...")

    info = get_video_info(url)
    if not info:
        await msg.edit_text("❌ خطا در دریافت اطلاعات ویدیو. لینک رو چک کن.")
        return

    title = info.get("title", "ویدیو")
    duration = info.get("duration", 0)
    duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "نامشخص"

    # ذخیره URL در context برای استفاده بعدی
    context.user_data["url"] = url
    context.user_data["title"] = title

    keyboard = [
        [
            InlineKeyboardButton("🎬 720p", callback_data="720"),
            InlineKeyboardButton("📱 480p", callback_data="480"),
            InlineKeyboardButton("📉 360p", callback_data="360"),
        ],
        [
            InlineKeyboardButton("🎵 فقط صدا (MP3)", callback_data="audio"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text(
        f"✅ ویدیو پیدا شد!\n\n"
        f"📹 عنوان: {title[:60]}\n"
        f"⏱ مدت: {duration_str}\n\n"
        f"کیفیت مورد نظر رو انتخاب کن:",
        reply_markup=reply_markup,
    )


async def handle_quality_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    quality = query.data
    url = context.user_data.get("url")
    title = context.user_data.get("title", "video")

    if not url:
        await query.edit_message_text("❌ لینک پیدا نشد. دوباره لینک بفرست.")
        return

    await query.edit_message_text(f"⬇️ در حال دانلود ({quality})...\nلطفاً صبر کن.")

    # تنظیمات دانلود
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:50]
    output_path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.%(ext)s")

    if quality == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_path,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
        }
    else:
        height = quality  # مثلاً 720
        ydl_opts = {
            "format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
            "outtmpl": output_path,
            "merge_output_format": "mp4",
            "quiet": True,
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if quality == "audio":
                filename = os.path.splitext(filename)[0] + ".mp3"
            else:
                filename = os.path.splitext(filename)[0] + ".mp4"

        # بررسی حجم فایل
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            os.remove(filename)
            await query.edit_message_text(
                f"❌ فایل خیلی بزرگه ({file_size_mb:.1f} MB).\n"
                f"کیفیت پایین‌تری انتخاب کن."
            )
            return

        await query.edit_message_text("📤 در حال آپلود...")

        with open(filename, "rb") as f:
            if quality == "audio":
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=f,
                    title=title[:60],
                    caption=f"🎵 {title[:60]}",
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=f,
                    caption=f"🎬 {title[:60]}",
                    supports_streaming=True,
                )

        os.remove(filename)
        await query.edit_message_text("✅ دانلود و ارسال با موفقیت انجام شد!")

    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.edit_message_text(f"❌ خطا در دانلود:\n{str(e)[:200]}")


# ===================== اجرا =====================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_quality_choice))

    logger.info("ربات شروع به کار کرد...")
    app.run_polling()


if __name__ == "__main__":
    main()
