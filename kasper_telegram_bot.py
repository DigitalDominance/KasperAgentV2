import os
import json
import logging
import asyncio
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
from subprocess import Popen, PIPE
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
db = client["kasper_bot"]
users_collection = db["users"]
transactions_collection = db["transactions"]

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

#######################################
# Wallet and KRC20 Functions
#######################################
node_process = Popen(
    ["node", "wallet_service.js"],
    stdin=PIPE,
    stdout=PIPE,
    stderr=PIPE,
    text=True
)

async def create_wallet():
    try:
        # Send a message to the Node.js process to create a wallet
        node_process.stdin.write("create_wallet\n")
        node_process.stdin.flush()

        # Read the response from the Node.js process
        response = node_process.stdout.readline().strip()
        wallet_data = json.loads(response)
        return wallet_data
    except Exception as e:
        print(f"Error creating wallet: {e}")
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

    # Check if the user already exists in the database
    user = users_collection.find_one({"_id": user_id})
    if not user:
        # If no wallet exists, create a new one
        wallet = await create_wallet()
        if wallet:
            # Save the wallet to the database
            users_collection.insert_one({
                "_id": user_id,
                "wallet_address": wallet["mainReceiveAddress"],
                "mnemonic": wallet["mnemonic"],
                "private_key": wallet["privateKey"],
                "credits": 0,  # Initialize with 0 credits
            })
            await update.message.reply_text(
                f"👻 Wallet created!\nAddress: {wallet['mainReceiveAddress']}\n\n"
                f"Save your mnemonic: {wallet['mnemonic']}\n"
                f"Private Key: {wallet['privateKey']}"
            )
        else:
            await update.message.reply_text("❌ Wallet creation failed.")
    else:
        # If a wallet already exists, send a welcome message with wallet details
        await update.message.reply_text(
            f"👻 Welcome back!\nYour wallet address: {user['wallet_address']}"
        )

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})
    if not user:
        await update.message.reply_text("❌ Please use /start first.")
        return

    wallet_address = user["wallet_address"]
    await update.message.reply_text(
        f"🔍 **Wallet Address:** `{wallet_address}`\n\n"
        f"⚖️ **Conversion Rate:** 200 KASPER = 1 Credit\n\n"
        "Send KASPER tokens to this address to top up your credits.\nUse `/endtopup` to calculate credits.",
        parse_mode="Markdown"
    )

async def endtopup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})
    if not user:
        await update.message.reply_text("❌ Please use /start first.")
        return

    wallet_address = user["wallet_address"]
    new_transactions = await fetch_krc20_operations(wallet_address)
    if new_transactions:
        total_amount = sum(tx["amount"] for tx in new_transactions)
        credits_added = int(total_amount * CREDIT_CONVERSION_RATE)
        users_collection.update_one({"_id": user_id}, {"$inc": {"credits": credits_added}})
        await update.message.reply_text(f"💰 {credits_added} credits added.")
    else:
        await update.message.reply_text("🔍 No new transactions detected.")

#######################################
# Main
#######################################
def main():
    check_ffmpeg()  # Ensure ffmpeg is installed
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("topup", topup_command))
    app.add_handler(CommandHandler("endtopup", endtopup_command))
    app.run_polling()

if __name__ == "__main__":
    main()
