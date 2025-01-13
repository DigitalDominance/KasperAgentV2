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
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles incoming text messages:
    - Checks rate limits and cooldowns.
    - Deducts credits for processing.
    - Generates AI responses and sends voice messages.
    """
    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    current_time = datetime.utcnow()

    # Fetch user details
    user = users_collection.find_one({"_id": user_id})
    if not user:
        await update.message.reply_text("❌ You need to use /start to initialize your account.")
        return

    # Enforce rate limit
    rate_info = USER_MESSAGE_LIMITS[user_id]
    if current_time >= rate_info["reset_time"]:
        rate_info["count"] = 0
        rate_info["reset_time"] = current_time + timedelta(hours=24)
        rate_info["last_message_time"] = None

    if rate_info["count"] >= MAX_MESSAGES_PER_USER:
        await update.message.reply_text(
            f"⛔ You have reached your daily limit of {MAX_MESSAGES_PER_USER} messages. Please try again tomorrow."
        )
        return

    # Enforce cooldown
    if rate_info["last_message_time"]:
        elapsed_time = (current_time - rate_info["last_message_time"]).total_seconds()
        if elapsed_time < COOLDOWN_SECONDS:
            remaining_time = int(COOLDOWN_SECONDS - elapsed_time)
            await update.message.reply_text(
                f"⏳ Please wait {remaining_time} more seconds before sending another message."
            )
            return

    # Check if user has enough credits
    if user["credits"] <= 0:
        await update.message.reply_text(
            "❌ You don't have enough credits to send a message. Please use /topup to add credits."
        )
        return

    # Deduct credits for this message
    users_collection.update_one({"_id": user_id}, {"$inc": {"credits": -1}})
    rate_info["count"] += 1
    rate_info["last_message_time"] = current_time

    try:
        # Notify user that the bot is processing
        processing_msg = await update.message.reply_text("👻 **KASPER is processing your request...** 👻", parse_mode="Markdown")

        # Generate AI response
        persona = context.user_data.get(
            "persona",
            "You are KASPER, a friendly ghost here to chat and help with Kasper-related questions."
        )
        ai_response = await generate_openai_response(user_text, persona)

        if not ai_response:
            ai_response = "I'm struggling to think of a response... (Ghostly shrug) 🤷‍♂️"

        # Convert AI response to voice using ElevenLabs
        mp3_data = await elevenlabs_tts(ai_response)
        if not mp3_data:
            await processing_msg.edit_text("❌ I couldn't generate an audio response.")
            return

        ogg_data = convert_mp3_to_ogg(mp3_data)
        ogg_data.name = "voice.ogg"  # Required for Telegram

        # Send voice and text response
        await update.message.reply_voice(voice=ogg_data)
        await update.message.reply_text(ai_response)

        # Update processing message
        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error in handle_text_message: {e}")
        logger.debug(traceback.format_exc())
        await update.message.reply_text("❌ An error occurred while processing your request.")

    # Notify user of remaining credits
    remaining_credits = users_collection.find_one({"_id": user_id})["credits"]
    await update.message.reply_text(f"💳 You have {remaining_credits} credits remaining.")
    
async def create_wallet():
    """
    Generates a wallet by invoking the wasm_rpc.js Node.js script.
    """
    try:
        # Use subprocess.run for synchronous execution to simplify debugging
        result = subprocess.run(
            ["node", "wasm_rpc.js"],
            capture_output=True,
            text=True,
            check=False  # Allow capturing errors
        )

        # Log raw outputs for debugging
        raw_stdout = result.stdout.strip()
        raw_stderr = result.stderr.strip()

        logger.debug(f"Node.js stdout: {raw_stdout}")
        logger.debug(f"Node.js stderr: {raw_stderr}")

        if result.returncode != 0:
            logger.error(f"Node.js script failed with exit code {result.returncode}")
            return None

        # Parse the JSON output
        wallet_data = json.loads(raw_stdout)
        formatted_wallet = {
            "mnemonic": json.loads(wallet_data["mnemonic"])["phrase"],
            "walletAddress": wallet_data["walletAddress"]["prefix"] + ":" + wallet_data["walletAddress"]["payload"],
            "xPrv": wallet_data["xPrv"],
            "firstChangeAddress": wallet_data["firstChangeAddress"]["prefix"] + ":" + wallet_data["firstChangeAddress"]["payload"],
            "secondReceiveAddress": wallet_data["secondReceiveAddress"]["prefix"] + ":" + wallet_data["secondReceiveAddress"]["payload"],
            "privateKey": wallet_data["privateKey"],
        }

        logger.info(f"Wallet successfully created: {formatted_wallet}")
        return formatted_wallet
    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to decode JSON output from Node.js script: {json_err}")
        return None
    except Exception as e:
        logger.error(f"An error occurred while creating the wallet: {e}")
        return None

#######################################
# Telegram Command Handlers
#######################################
async def start_command(update, context):
    user_id = update.effective_user.id
    user = users_collection.find_one({"_id": user_id})

    if not user:
        # Directly call the function, no need for `await` since it's no longer asynchronous
        wallet = create_wallet()
        if wallet:
            users_collection.insert_one({
                "_id": user_id,
                "wallet_address": wallet["walletAddress"],
                "mnemonic": wallet["mnemonic"],
                "xPrv": wallet["xPrv"],  # Store the xPrv for recovery if needed
                "credits": 0,
            })
            await update.message.reply_text(
                f"👻 Wallet successfully created!\n\n"
                f"**Address:** `{wallet['walletAddress']}`\n"
                f"**Mnemonic:** `{wallet['mnemonic']}`\n\n"
                f"💾 Save your mnemonic securely!"
            )
        else:
            await update.message.reply_text("❌ Failed to create a wallet. Please try again later.")
            return
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
    """
    /endtopup command to check the user's wallet balance.
    """
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
