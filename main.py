import os
import re
import html
import zipfile
import logging
import asyncio
from io import BytesIO
from datetime import datetime

import qrcode
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ===============================
# ENV CONFIG
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))
PUBLIC_URL = os.getenv("PUBLIC_URL")  # https://xxx.up.railway.app

BASE_DIR = "data"
os.makedirs(BASE_DIR, exist_ok=True)

# ===============================
# LOGGING
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ===============================
# ALLOWED USERS
# ===============================
ALLOWED_USERS_FILE = "allowed_users.txt"

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
    if user.id not in allowed_users:
        await update.message.reply_text("🚫 Sizda ruxsat yo‘q.")
        await context.bot.send_message(
            SUPER_ADMIN_ID,
            f"⚠️ Yangi foydalanuvchi:\nID: {user.id}\n@{user.username}"
        )
        return

    await update.message.reply_text(
        "✅ Salom!\n38 ta belgidan iborat kod yuboring."
    )

async def generate_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in allowed_users:
        return

    text = update.message.text.strip()

    if len(text) != 38:
        await update.message.reply_text("❌ Kod 38 ta belgidan iborat bo‘lishi shart.")
        return

    if not re.match(r'^[\x20-\x7E]+$', text):
        await update.message.reply_text("❌ Kod format xato.")
        return

    user_folder = os.path.join(BASE_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    with open(os.path.join(user_folder, f"{today}.txt"), "a") as f:
        f.write(text + "\n")

    qr = qrcode.make(text)
    bio = BytesIO()
    qr.save(bio, format="PNG")
    bio.seek(0)

    await update.message.reply_photo(
        photo=bio,
        caption=f"<code>{html.escape(text)}</code>",
        parse_mode="HTML"
    )

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

async def getdata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return

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

# ===============================
# FLASK + WEBHOOK
# ===============================
flask_app = Flask(__name__)
tg_app = Application.builder().token(BOT_TOKEN).build()

# Webhook route
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.json, tg_app.bot)
    asyncio.run(tg_app.process_update(update))
    return "OK"

# Webhook set qilish
async def set_webhook():
    await tg_app.bot.set_webhook(f"{PUBLIC_URL}/{BOT_TOKEN}")
    logger.info("Webhook o‘rnatildi ✅")

# ===============================
# START SERVER
# ===============================
def main():
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("allow", allow_user))
    tg_app.add_handler(CommandHandler("getdata", getdata))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_qr))

    asyncio.run(set_webhook())
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    main()
