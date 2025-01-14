import os
import json
import logging
import asyncio
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
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
async def create_wallet():
    """
    Invokes the wasm_rpc.js Node.js script using a child process to generate a wallet.
    """
    try:
        # Use asyncio subprocess to call the Node.js script
        process = await asyncio.create_subprocess_exec(
            "node", "wasm_rpc.js",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # Handle errors during wallet creation
        if process.returncode != 0:
            logger.error(f"Wallet creation failed: {stderr.decode()}")
            return None

        # Parse the JSON output from Node.js
        wallet_data = json.loads(stdout.decode().strip())
        return {
            "mnemonic": wallet_data["mnemonic"],
            "walletAddress": wallet_data["walletAddress"],
            "xPrv": wallet_data["xPrv"],
            "firstChangeAddress": wallet_data["firstChangeAddress"],
            "secondReceiveAddress": wallet_data["secondReceiveAddress"],
            "privateKey": wallet_data["privateKey"],
        }
    except Exception as e:
        logger.error(f"Error creating wallet: {e}")
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
    """
    /start command to initialize a user's wallet and profile.
    """
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})

    if not user:
        wallet = await create_wallet()
        if wallet:
            users_collection.insert_one({
                "_id": user_id,
                "wallet_address": wallet["walletAddress"],
                "mnemonic": wallet["mnemonic"],
                "xPrv": wallet["xPrv"],
                "credits": 0,
            })
            await update.message.reply_text(
                f"👻 Wallet successfully created!\n\n"
                f"**Address:** `{wallet['walletAddress']}`\n"
                f"**Mnemonic:** `{wallet['mnemonic']}`\n\n"
                f"💾 Save your mnemonic securely!"
            )
        else:
            await update.message.reply_text("❌ Wallet creation failed.")
    else:
        await update.message.reply_text(f"👻 Welcome back! Your wallet: {user['wallet_address']}")

    USER_MESSAGE_LIMITS[user_id]["count"] = 0
    USER_MESSAGE_LIMITS[user_id]["reset_time"] = datetime.utcnow() + timedelta(hours=24)
    await update.message.reply_text("👻 KASPER is ready to assist you!")


async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /topup command to check for new KRC20 transactions and credit the user's account.
    """
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})
    if not user:
        await update.message.reply_text("❌ Please use /start first.")
        return

    wallet_address = user["wallet"]["walletAddress"]
    conversion_rate_message = f"⚖️ **Conversion Rate:** 200 KASPER = 1 Credit"

    await update.message.reply_text(
        f"🔍 Starting a top-up scan...\n\n"
        f"👻 **Wallet Address:** `{wallet_address}`\n\n"
        f"{conversion_rate_message}\n\n"
        f"💡 Send your KASPER tokens to this address to top up your credits.\n"
        f"👉 Use `/endtopup` to finish and calculate your credits when you're done!",
        parse_mode="Markdown"
    )

    # Start scanning for new transactions (asynchronous)
    new_transactions = await fetch_krc20_operations(wallet_address)
    if new_transactions:
        total_amount = sum(tx["amount"] for tx in new_transactions)
        credits_added = int(total_amount * CREDIT_CONVERSION_RATE)
        users_collection.update_one({"_id": user_id}, {"$inc": {"credits": credits_added}})
        await update.message.reply_text(
            f"💰 New transactions detected! {credits_added} credits have been added so far."
        )
    else:
        await update.message.reply_text("🔍 No new transactions detected yet. Keep sending your KASPER tokens!")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /balance command to display the user's current credit balance.
    """
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})
    if not user:
        await update.message.reply_text("❌ Please use /start first.")
        return

    credits = user["credits"]
    await update.message.reply_text(f"💳 Your current balance is {credits} credits.")

async def endtopup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /endtopup command to manually trigger a scan for transactions and end the top-up period.
    """
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})
    if not user:
        await update.message.reply_text("❌ Please use /start first.")
        return

    wallet_address = user["wallet"]["walletAddress"]
    new_transactions = await fetch_krc20_operations(wallet_address)
    if new_transactions:
        total_amount = sum(tx["amount"] for tx in new_transactions)
        credits_added = int(total_amount * CREDIT_CONVERSION_RATE)
        users_collection.update_one({"_id": user_id}, {"$inc": {"credits": credits_added}})
        await update.message.reply_text(
            f"💰 Final scan complete! {credits_added} credits were added."
        )
    else:
        await update.message.reply_text("🔍 Final scan complete! No new transactions.")
#######################################
# Main
#######################################
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("topup", topup_command))
    app.run_polling()

if __name__ == "__main__":
    main()
