import os
import json
import signal
import sys
import logging
import asyncio
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
from subprocess import Popen, PIPE
import traceback
from db_manager import DBManager

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
from telegram.error import TelegramError

#######################################
# Environment Variables
#######################################
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVEN_LABS_API_KEY = os.getenv("ELEVEN_LABS_API_KEY", "")
ELEVEN_LABS_VOICE_ID = os.getenv("ELEVEN_LABS_VOICE_ID", "")
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
db_manager = DBManager()

async def handle_text_message(update, context):
    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    user = db.get_user(user_id)

    if not user or user.get("credits", 0) <= 0:
        await update.message.reply_text("❌ You have no credits remaining.")
        return

    try:
        await update.message.reply_text("👻 KASPER is thinking...")
        ai_response = await generate_openai_response(user_text)
        mp3_audio = await elevenlabs_tts(ai_response)
        ogg_audio = convert_mp3_to_ogg(mp3_audio)
        db.update_user_credits(user_id, user["credits"] - 1)
        await update.message.reply_text(ai_response)
        await update.message.reply_voice(voice=ogg_audio)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ An error occurred.")
#######################################
# Check ffmpeg Availability
#######################################
def check_ffmpeg():
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logger.info("ffmpeg is installed and accessible.")
    except Exception as e:
        logger.error("ffmpeg is not installed or not accessible. Please install it.")
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
            ogg_buffer, format="ogg", codec="libopus", bitrate="64k"
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
    payload = {"text": text, "model_id": "eleven_turbo_v2"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_LABS_VOICE_ID}",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Error in ElevenLabs TTS: {e}")
            return b""
            
async def generate_openai_response(user_text: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_text}
        ]
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Error in OpenAI Chat Completion: {e}")
            return "❌ An error occurred while generating a response."
#######################################
# Wallet and KRC20 Functions
#######################################
def create_wallet():
    logger.info("Creating wallet via Node.js...")
    try:
        process = subprocess.Popen(
            ["node", "wasm_rpc.js", "createWallet"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate()
        logger.info(f"Raw stdout: {stdout}")
        logger.error(f"Raw stderr: {stderr}")
        if process.returncode != 0:
            logger.error("Node.js script failed.")
            return None
        return json.loads(stdout.strip())  # Try parsing the output
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing wallet creation response: {e}")
        return None
    except Exception as e:
        logger.error(f"Error in wallet creation: {e}")
        return None


async def fetch_krc20_operations(wallet_address: str):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(KRC20_API_URL)
            response.raise_for_status()
            operations = response.json().get("result", [])
            new_transactions = []
            for op in operations:
                if op["to"] == wallet_address and op["op"] == "TRANSFER":
                    if not transactions_collection.find_one({"hashRev": op["hashRev"]}):
                        amount = int(op["amt"]) / 1e8
                        transaction = {"amount": amount, "hashRev": op["hashRev"]}
                        transactions_collection.insert_one(transaction)
                        new_transactions.append(transaction)
            return new_transactions
    except Exception as e:
        logger.error(f"KRC20 fetch error: {e}")
        return []

#######################################
# Telegram Command Handlers
#######################################
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        user = db_manager.get_user(user_id)
        if not user:
            wallet_data = create_wallet()
            if wallet_data.get("success"):
                wallet_address = wallet_data.get("receivingAddress")
                private_key = wallet_data.get("xPrv")

                db_manager.create_user(user_id, wallet_address, private_key, credits=3)
                await update.message.reply_text(
                    f"👻 Welcome to Kasper AI! Your wallet address is: {wallet_address}. You have 3 free credits."
                )
            else:
                await update.message.reply_text("⚠️ Failed to create a wallet. Please try again later.")
        else:
            await update.message.reply_text(
                f"👋 Welcome back! Your wallet address is: {user['wallet_address']}. You have {user['credits']} credits."
            )
    except Exception as e:
        logger.error(f"Error in start_command for user {user_id}: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again later.")

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db_manager.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Please use /start first.")
        return

    wallet_address = user["wallet_address"]
    await update.message.reply_text(
        f"🔍 **Wallet Address:** `{wallet_address}`\n\n"
        f"⚖️ **Conversion Rate:** 200 KASPER = 1 Credit\n\n"
        "Send KASPER tokens to this address to top up your credits.",
        parse_mode="Markdown"
    )

async def endtopup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db_manager.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Please use /start first.")
        return

    wallet_address = user["wallet_address"]
    new_transactions = await fetch_krc20_operations(wallet_address)
    if new_transactions:
        total_amount = sum(tx["amount"] for tx in new_transactions)
        credits_added = int(total_amount * CREDIT_CONVERSION_RATE)
        db_manager.update_credits(user_id, credits_added)
        await update.message.reply_text(f"💰 {credits_added} credits added.")
    else:
        await update.message.reply_text("🔍 No new transactions detected.")

#######################################
# Main
#######################################
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("topup", topup_command))
    app.add_handler(CommandHandler("endtopup", endtopup_command))

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Bot is running...")
    app.run_polling()

def shutdown(signum, frame):
    logger.info("Shutting down gracefully...")
    db_manager.close()
    sys.exit(0)

if __name__ == "__main__":
    main()
