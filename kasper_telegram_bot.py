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
KRC20_API_URL = "https://api.kasplex.org/v1/krc20/oplist"

MAX_MESSAGES_PER_USER = int(os.getenv("MAX_MESSAGES_PER_USER", "20"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "15"))
CREDIT_CONVERSION_RATE = 200  # 1 credit = 200 KASPER

#######################################
# Logging Setup
#######################################
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

#######################################
# Database Setup
#######################################
client = MongoClient(MONGO_URI)
db = client["kasper_bot"]
users_collection = db["users"]
transactions_collection = db["transactions"]

#######################################
# Rate Limits
#######################################
USER_MESSAGE_LIMITS = defaultdict(lambda: {
    "count": 0,
    "reset_time": datetime.utcnow() + timedelta(hours=24),
    "last_message_time": None,
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
    """
    Convert MP3 bytes to OGG (Opus) format for Telegram voice notes.
    """
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
# OpenAI Messaging
#######################################
async def generate_openai_response(user_text: str, persona: str) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4",
        "messages": [{"role": "system", "content": persona}, {"role": "user", "content": user_text}],
        "temperature": 0.8,
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error in OpenAI API: {e}")
            return "I'm having trouble thinking... 😞"

#######################################
# Wallet Management
#######################################
def create_wallet():
    try:
        process = subprocess.Popen(
            ["node", "wasm_rpc.js"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            return json.loads(stdout)
        else:
            logger.error(f"Error creating wallet: {stderr.decode()}")
            return None
    except Exception as e:
        logger.error(f"Failed to create wallet: {e}")
        return None

async def fetch_krc20_operations(wallet_address: str):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(KRC20_API_URL)
            response.raise_for_status()
            data = response.json()
            operations = data.get("result", [])

            new_transactions = []
            for op in operations:
                if op["to"] == wallet_address and op["op"] == "TRANSFER":
                    if op["txAccept"] == "true" and op["opAccept"] == "true":
                        if not transactions_collection.find_one({"hashRev": op["hashRev"]}):
                            amount = int(op["amt"]) / 1e8
                            transaction = {
                                "wallet": wallet_address,
                                "hashRev": op["hashRev"],
                                "amount": amount,
                                "mtsAdd": op["mtsAdd"],
                                "feeRev": int(op["feeRev"]) / 1e8,
                            }
                            transactions_collection.insert_one(transaction)
                            new_transactions.append(transaction)

            return new_transactions
    except Exception as e:
        logger.error(f"Error fetching KRC-20 operations: {e}")
        return []

async def get_wallet_balance(wallet_address: str):
    try:
        await fetch_krc20_operations(wallet_address)
        transactions = transactions_collection.find({"wallet": wallet_address})
        return sum(tx["amount"] for tx in transactions)
    except Exception as e:
        logger.error(f"Error calculating wallet balance: {e}")
        return 0

#######################################
# Telegram Command Handlers
#######################################
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})

    if not user:
        wallet = create_wallet()
        if wallet:
            users_collection.insert_one({
                "_id": user_id,
                "wallet_address": wallet["address"],
                "mnemonic": wallet["mnemonic"],
                "credits": 0,
            })
            await update.message.reply_text(f"👻 Wallet created! Your address: {wallet['address']}")
        else:
            await update.message.reply_text("❌ Failed to create a wallet. Please try again later.")
            return
    else:
        await update.message.reply_text(f"👻 Welcome back! Your wallet: {user['wallet_address']}")

    USER_MESSAGE_LIMITS[user_id]["count"] = 0
    USER_MESSAGE_LIMITS[user_id]["reset_time"] = datetime.utcnow() + timedelta(hours=24)
    await update.message.reply_text("👻 KASPER is ready to assist you!")

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})

    if not user:
        await update.message.reply_text("❌ You need to start with /start to generate a wallet first.")
        return

    wallet_address = user["wallet_address"]
    new_transactions = await fetch_krc20_operations(wallet_address)
    if new_transactions:
        total_amount = sum(tx["amount"] for tx in new_transactions)
        users_collection.update_one(
            {"_id": user_id},
            {"$inc": {"credits": int(total_amount * CREDIT_CONVERSION_RATE)}}
        )
        await update.message.reply_text(f"💰 Top-up complete! You received {total_amount} KASPER.")
    else:
        await update.message.reply_text("🔍 No new transactions found.")

async def endtopup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})

    if not user:
        await update.message.reply_text("❌ You need to start with /start to generate a wallet first.")
        return

    balance = await get_wallet_balance(user["wallet_address"])
    await update.message.reply_text(f"🏦 Your wallet balance is {balance} KASPER.")

#######################################
# Main
#######################################
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("topup", topup_command))
    application.add_handler(CommandHandler("endtopup", endtopup_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.run_polling()

if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
