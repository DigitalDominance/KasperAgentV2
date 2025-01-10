
import os
import json
import logging
import asyncio
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
import signal
import traceback

import httpx
from pydub import AudioSegment

from telegram.ext import ApplicationBuilder, CommandHandler
from db_manager import DBManager
from wallet_backend import WalletBackend

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVEN_LABS_API_KEY = os.getenv("ELEVEN_LABS_API_KEY", "")
ELEVEN_LABS_VOICE_ID = os.getenv("ELEVEN_LABS_VOICE_ID", "0whGLe6wyQ2fwT9M40ZY")
MAX_MESSAGES_PER_USER = int(os.getenv("MAX_MESSAGES_PER_USER", "20"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "15"))
CREDIT_CONVERSION_RATE = 100  # 1 credit = 100 KASPER

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize dependencies
db = DBManager()
wallet = WalletBackend()

# Rate Limit: 20 messages / 24h
USER_MESSAGE_LIMITS = defaultdict(lambda: {
    "count": 0,
    "reset_time": datetime.utcnow() + timedelta(hours=24),
    "last_message_time": None
})

# Background task to monitor deposits
async def monitor_deposits():
    while True:
        users = db.users.find()
        for user in users:
            wallet_address = user["wallet"]
            transactions = wallet.check_transactions(wallet_address)

            for tx in transactions:
                amount = tx.get("amount", 0)
                if amount >= CREDIT_CONVERSION_RATE:
                    credits = amount // CREDIT_CONVERSION_RATE

                    # Update user credits and mark transaction as processed
                    db.update_user_credits(user["user_id"], user["credits"] + credits)
                    logger.info(f"Credited {credits} to user {user['user_id']} for {amount} KASPER.")

        await asyncio.sleep(30)  # Check every 30 seconds

# Convert MP3 -> OGG
def convert_mp3_to_ogg(mp3_data: bytes) -> BytesIO:
    try:
        mp3_file = BytesIO(mp3_data)
        segment = AudioSegment.from_file(mp3_file, format="mp3")
        ogg_buffer = BytesIO()
        segment.export(
            ogg_buffer,
            format="ogg",
            codec="libopus",
            bitrate="64k",
            parameters=["-vbr", "on"]
        )
        ogg_buffer.seek(0)
        return ogg_buffer
    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        return BytesIO()

# ElevenLabs TTS
async def elevenlabs_tts(text: str, user_id: int):
    user = db.get_user(user_id)
    if not user or user.get("credits", 0) <= 0:
        return None, "❌ You have no credits remaining. Please top up to use this feature."

    headers = {
        "xi-api-key": ELEVEN_LABS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.75,
            "similarity_boost": 0.75
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_LABS_VOICE_ID}",
                headers=headers,
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            db.update_user_credits(user_id, user["credits"] - 1)  # Deduct 1 credit
            return resp.content, None
        except Exception as e:
            logger.error(f"Error in ElevenLabs TTS: {e}")
            return None, "❌ An error occurred while processing your request."

# OpenAI Chat Completion
async def generate_openai_response(user_text: str, persona: str, user_id: int):
    user = db.get_user(user_id)
    if not user or user.get("credits", 0) <= 0:
        return "❌ You have no credits remaining. Please top up to use this feature."

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": persona},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.8,
        "max_tokens": 1024
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            db.update_user_credits(user_id, user["credits"] - 1)  # Deduct 1 credit
            data = resp.json()
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            logger.error(f"Error in OpenAI Chat Completion: {e}")
            return "❌ An error occurred while processing your request."

# Command Handlers
async def start(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        wallet_address = wallet.generate_wallet(user_id)
        db.add_user(user_id, credits=3, wallet=wallet_address)
        await update.message.reply_text(
            f"Welcome to Kasper AI! You have 3 free credits. Your deposit wallet is: {wallet_address}"
        )
    else:
        await update.message.reply_text(
            f"Welcome back! You have {user['credits']} credits. Your deposit wallet is: {user['wallet']}"
        )

async def topup(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please use /start first to register.")
        return

    wallet_address = user['wallet']
    await update.message.reply_text(
        f"Send KASPER tokens to your deposit wallet: {wallet_address}. 1 Credit = 100 KASPER."
    )

# Main function to run the bot
def main():
    check_ffmpeg()

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("topup", topup))

    # Start background tasks
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_deposits())

    logger.info("Starting Kasper AI Bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
