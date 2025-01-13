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
from pymongo import MongoClient

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError, BadRequest

#######################################
# Environment Variables
#######################################
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVEN_LABS_API_KEY = os.getenv("ELEVEN_LABS_API_KEY", "")
ELEVEN_LABS_VOICE_ID = os.getenv("ELEVEN_LABS_VOICE_ID", "0whGLe6wyQ2fwT9M40ZY")
MONGO_URI = os.getenv("MONGO_URI", "")


MAX_MESSAGES_PER_USER = int(os.getenv("MAX_MESSAGES_PER_USER", "20"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "15"))
CREDIT_CONVERSION_RATE = 200  # 1 credit = 200 KASPER

#######################################
# Logging Setup
#######################################
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

#######################################
# Database Setup
#######################################
client = MongoClient(MONGO_URI)
db = client['kasper_bot']
users_collection = db['users']
transactions_collection = db['transactions']

#######################################
# Rate Limit: 20 messages / 24h
#######################################
USER_MESSAGE_LIMITS = defaultdict(lambda: {
    "count": 0,
    "reset_time": datetime.utcnow() + timedelta(hours=24),
    "last_message_time": None
})

#######################################
# Check ffmpeg Availability
#######################################
def check_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("ffmpeg is installed and accessible.")
    except Exception as e:
        logger.error("ffmpeg is not installed or not accessible.")
        raise e

#######################################
# Convert MP3 -> OGG
#######################################
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
        logger.info("MP3 successfully converted to OGG.")
        return ogg_buffer
    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        return BytesIO()

#######################################
# ElevenLabs TTS
#######################################
async def elevenlabs_tts(text: str) -> bytes:
    headers = {"xi-api-key": ELEVEN_LABS_API_KEY, "Content-Type": "application/json"}
    payload = {"text": text, "model_id": "eleven_turbo_v2", "voice_settings": {"stability": 0.75, "similarity_boost": 0.75}}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_LABS_VOICE_ID}",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Error in ElevenLabs TTS: {e}")
            return b""

#######################################
# OpenAI Chat Completion
#######################################
async def generate_openai_response(user_text: str, persona: str) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4",
        "messages": [{"role": "system", "content": persona}, {"role": "user", "content": user_text}],
        "temperature": 0.8
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Error in OpenAI API: {e}")
            return "I'm having trouble thinking... 😞"

#######################################
# Telegram Handlers
#######################################
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_collection.update_one({"_id": user_id}, {"$setOnInsert": {"credits": 0}}, upsert=True)
    USER_MESSAGE_LIMITS[user_id]["count"] = 0
    USER_MESSAGE_LIMITS[user_id]["reset_time"] = datetime.utcnow() + timedelta(hours=24)
    await update.message.reply_text("👻 Welcome! KASPER is here to assist you!")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    if not user_text:
        return
    limit_info = USER_MESSAGE_LIMITS[user_id]
    current_time = datetime.utcnow()
    if limit_info["count"] >= MAX_MESSAGES_PER_USER:
        await update.message.reply_text("Message limit exceeded!")
        return
    limit_info["count"] += 1
    persona = "You're KASPER, the friendly ghost..."
    response = await generate_openai_response(user_text, persona)
    mp3_data = await elevenlabs_tts(response)
    ogg_data = convert_mp3_to_ogg(mp3_data)
    ogg_data.name = "voice.ogg"
    await update.message.reply_voice(ogg_data)
    await update.message.reply_text(response)

#######################################
# Main
#######################################
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.run_polling()

if __name__ == "__main__":
    main()
