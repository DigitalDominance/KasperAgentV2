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

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db_manager.get_user(user_id)
    user_text = update.message.text.strip()

    if not user:
        await update.message.reply_text("❌ Please use /start to create a wallet before interacting.")
        return

    if user["credits"] <= 0:
        await update.message.reply_text("❌ You have no credits remaining. Use /topup to add credits.")
        return

    try:
        await update.message.reply_text("👻 KASPER is thinking... 🌀")
        ai_response = await generate_openai_response(user_text)
        mp3_audio = await elevenlabs_tts(ai_response)
        ogg_audio = convert_mp3_to_ogg(mp3_audio)

        # Deduct one credit and update the database
        db_manager.update_credits(user_id, -1)

        # Send AI response and voice message
        await update.message.reply_text(ai_response)
        await update.message.reply_voice(voice=ogg_audio)

    except Exception as e:
        logger.error(f"Error handling text message: {e}")
        await update.message.reply_text("❌ An error occurred while processing your request.")

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
    """
    Fetch new KRC-20 transfer operations for a specific wallet address.
    
    Args:
        wallet_address (str): The wallet address to filter transactions for.
    
    Returns:
        List[dict]: A list of new transactions detected.
    """
    try:
        # Define the API URL with the wallet address and ticker 'KASPER'
        api_url = f"https://api.kasplex.org/v1/krc20/oplist?address={wallet_address}&tick=KASPER"

        logger.info(f"Fetching KRC20 transactions for wallet: {wallet_address}")

        async with httpx.AsyncClient() as client:
            response = await client.get(api_url)
            response.raise_for_status()
            data = response.json()

            # Extract transactions from the API response
            operations = data.get("result", [])
            new_transactions = []

            for op in operations:
                # Process only 'TRANSFER' operations that are accepted
                if op["op"] == "TRANSFER" and op.get("opAccept") == "1":
                    tx_hash = op["hashRev"]

                    # Check if the transaction is already recorded
                    if not db_manager.transaction_exists(tx_hash):
                        # Parse the amount and other transaction details
                        amount = int(op["amt"]) / 1e8  # Convert from sompi to KAS
                        transaction = {
                            "amount": amount,
                            "hashRev": tx_hash,
                            "from": op["from"],
                            "to": op["to"],
                            "timestamp": int(op["mtsAdd"]),
                        }

                        # Save the new transaction to the database
                        db_manager.add_transaction(transaction)
                        new_transactions.append(transaction)

            logger.info(f"New transactions found: {new_transactions}")
            return new_transactions

    except httpx.RequestError as e:
        logger.error(f"HTTP error while fetching KRC20 transactions: {e}")
        return []
    except KeyError as e:
        logger.error(f"Error processing transaction data: Missing key {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in fetch_krc20_operations: {e}")
        return []


#######################################
# Telegram Command Handlers
#######################################
async def start_command(update, context):
    user_id = update.effective_user.id
    try:
        # Check if the user already exists in the database
        user = db_manager.get_user(user_id)
        if not user:
            # Inform the user that the wallet creation is in progress
            creating_message = await update.message.reply_text(
                "👻 Hang tight! We're conjuring your ghostly wallet... This may take a few seconds. 🌀"
            )

            # Log wallet creation process
            logger.info("Creating wallet for a new user...")

            # Call the Node.js wallet creation process (synchronously)
            wallet_data = create_wallet()  # No `await` here as `create_wallet` is not async

            if wallet_data and wallet_data.get("success"):
                wallet_address = wallet_data.get("receivingAddress")
                private_key = wallet_data.get("xPrv")
                mnemonic = wallet_data.get("mnemonic")

                # Ensure all required fields are available
                if not wallet_address or not private_key or not mnemonic:
                    raise ValueError("Incomplete wallet data")

                # Save the user in the database with 3 free credits
                db_manager.create_user(
                    telegram_id=user_id,
                    wallet_address=wallet_address,
                    private_key=private_key,
                    mnemonic=mnemonic,
                    credits=3
                )

                # Update the ghostly message with the wallet details
                await creating_message.edit_text(
                    f"👻 Welcome to Kasper AI! Your wallet has been conjured:\n\n"
                    f"💼 **Wallet Address:** `{wallet_address}`\n"
                    f"🔑 **Mnemonic:** `{mnemonic}`\n\n"
                    f"⚠️ **Important:** Save your mnemonic phrase securely. You will need it to recover your wallet.\n\n"
                    f"🎁 You have been granted **3 free credits** to get started!",
                    parse_mode="Markdown"
                )
            else:
                # Handle wallet creation failure
                error_message = wallet_data.get("error") if wallet_data else "Unknown error"
                logger.error(f"Failed to create wallet: {error_message}")
                await creating_message.edit_text("⚠️ Failed to create a wallet. Please try again later.")
        else:
            # If the user already exists, greet them and show their wallet and credits
            await update.message.reply_text(
                f"👋 Welcome back!\n\n"
                f"💼 **Wallet Address:** `{user['wallet_address']}`\n"
                f"🎯 **Credits:** `{user['credits']}`\n\n"
                f"Use /topup to add more credits and explore Kasper AI!",
                parse_mode="Markdown"
            )
    except Exception as e:
        # Log and handle unexpected errors
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

    # Fetch new transactions for the wallet address
    new_transactions = await fetch_krc20_operations(wallet_address)

    if new_transactions:
        total_amount = sum(tx["amount"] for tx in new_transactions)
        credits_added = int(total_amount * CREDIT_CONVERSION_RATE)

        # Update user credits in the database
        db_manager.update_credits(user_id, credits_added)

        await update.message.reply_text(
            f"💰 You've received **{total_amount:.2f} KASPER**, adding **{credits_added} credits** to your account.\n\n"
            "Thank you for topping up!"
        )
    else:
        await update.message.reply_text("🔍 No new transactions detected. Please try again later.")


#######################################
# Main
#######################################
def main():
    # Initialize the Telegram bot application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("topup", topup_command))
    app.add_handler(CommandHandler("endtopup", endtopup_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

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
