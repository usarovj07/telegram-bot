import os
import re
import html
import zipfile
import logging
from io import BytesIO
from datetime import datetime

import qrcode
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===============================
# ENV CONFIG
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))
PUBLIC_URL = os.getenv("PUBLIC_URL")

BASE_DIR = "data"
os.makedirs(BASE_DIR, exist_ok=True)

ALLOWED_USERS_FILE = "allowed_users.txt"
USER_LOG = "user_activity.log"

# ===============================
# LOGGING
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

user_logger = logging.getLogger("user_logger")
user_handler = logging.FileHandler(USER_LOG, encoding="utf-8")
user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
user_logger.addHandler(user_handler)
user_logger.setLevel(logging.INFO)

# ===============================
# ALLOWED USERS
# ===============================
def load_allowed_users():
    if not os.path.exists(ALLOWED_USERS_FILE):
        return {SUPER_ADMIN_ID}
    with open(ALLOWED_USERS_FILE, "r") as f:
        return set(map(int, f.read().splitlines()))

def save_allowed_users(users: set):
    with open(ALLOWED_USERS_FILE, "w") as f:
        f.write("\n".join(map(str, users)))

allowed_users = load_allowed_users()

# ===============================
# BOT HANDLERS
# ===============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    fullname = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = f"@{user.username}" if user.username else "—"

    if user.id not in allowed_users:
        await update.message.reply_text(
            f"🚫 Sizda ruxsat yo‘q.\n"
            f"🆔 {user.id}\n"
            f"👤 {fullname}\n"
            f"🔗 {username}"
        )

        await context.bot.send_message(
            SUPER_ADMIN_ID,
            f"⚠️ Ruxsatsiz foydalanuvchi:\n"
            f"🆔 {user.id}\n"
            f"👤 {fullname}\n"
            f"🔗 {username}"
        )
        return

    user_logger.info(f"START | {user.id} | {fullname} | {username}")
    await update.message.reply_text("✅ Salom! 38 ta belgidan iborat kod yuboring.")

async def generate_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in allowed_users:
        return

    text = update.message.text.strip()

    if len(text) != 38:
        await update.message.reply_text("❌ Kod 38 ta belgidan iborat bo‘lishi kerak.")
        return

    if not re.match(r'^[\x20-\x7E]+$', text):
        await update.message.reply_text("❌ Kod format xato.")
        return

    user_folder = os.path.join(BASE_DIR, str(user.id))
    os.makedirs(user_folder, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    with open(os.path.join(user_folder, f"{today}.txt"), "a", encoding="utf-8") as f:
        f.write(text + "\n")

    qr = qrcode.make(text)
    bio = BytesIO()
    qr.save(bio, format="PNG")
    bio.seek(0)

    await update.message.reply_photo(
        photo=bio,
        caption=f"<code>{html.escape(text)}</code>",
        parse_mode="HTML",
    )

    user_logger.info(f"QR | {user.id} | {text}")

async def allow_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return

    try:
        new_id = int(context.args[0])
        allowed_users.add(new_id)
        save_allowed_users(allowed_users)
        await update.message.reply_text(f"✅ {new_id} qo‘shildi.")
    except:
        await update.message.reply_text("❌ ID noto‘g‘ri.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return

    try:
        rem_id = int(context.args[0])
        if rem_id in allowed_users:
            allowed_users.remove(rem_id)
            save_allowed_users(allowed_users)
            await update.message.reply_text(f"❌ {rem_id} bloklandi.")
        else:
            await update.message.reply_text("⚠️ Bu ID ro‘yxatda yo‘q.")
    except:
        await update.message.reply_text("❌ ID noto‘g‘ri.")

async def users_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return

    await update.message.reply_text(
        f"📌 Ruxsatli foydalanuvchilar soni: {len(allowed_users)}\n\n"
        + "\n".join(map(str, allowed_users))
    )

async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return

    if not os.path.exists(USER_LOG):
        await update.message.reply_text("📄 Log mavjud emas.")
        return

    with open(USER_LOG, "r", encoding="utf-8") as f:
        content = f.read()

    CHUNK = 3500
    for i in range(0, len(content), CHUNK):
        await update.message.reply_text(content[i:i+CHUNK])

async def getdata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return

    try:
        target_id = context.args[0]
        folder = os.path.join(BASE_DIR, target_id)

        if not os.path.exists(folder):
            await update.message.reply_text("📂 Ma’lumot yo‘q.")
            return

        zip_path = f"{target_id}.zip"
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for file in os.listdir(folder):
                zipf.write(os.path.join(folder, file), file)

        await update.message.reply_document(open(zip_path, "rb"))
        os.remove(zip_path)
    except:
        await update.message.reply_text("❌ Xatolik yuz berdi.")

# ===============================
# FASTAPI + TELEGRAM
# ===============================
app = FastAPI()
tg_app = Application.builder().token(BOT_TOKEN).build()

tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("allow", allow_user))
tg_app.add_handler(CommandHandler("remove", remove_user))
tg_app.add_handler(CommandHandler("users_count", users_count))
tg_app.add_handler(CommandHandler("show_users", show_users))
tg_app.add_handler(CommandHandler("getdata", getdata))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_qr))

@app.on_event("startup")
async def on_startup():
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.bot.set_webhook(f"{PUBLIC_URL}/{BOT_TOKEN}")
    logger.info("Webhook o‘rnatildi ✅")

@app.post(f"/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}
