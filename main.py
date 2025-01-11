import os
import logging
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO

import httpx
from pydub import AudioSegment
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from db_manager import DBManager
from wallet_backend import WalletBackend

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVEN_LABS_API_KEY = os.getenv("ELEVEN_LABS_API_KEY", "")
ELEVEN_LABS_VOICE_ID = os.getenv("ELEVEN_LABS_VOICE_ID", "0whGLe6wyQ2fwT9M40ZY")
MAIN_WALLET_ADDRESS = os.getenv("MAIN_WALLET_ADDRESS", "")
MAIN_WALLET_PRIVATE_KEY = os.getenv("MAIN_WALLET_PRIVATE_KEY", "")
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

USER_MESSAGE_LIMITS = defaultdict(lambda: {
    "count": 0,
    "reset_time": datetime.utcnow() + timedelta(hours=24),
    "last_message_time": None
})

# Background task to monitor balances
async def monitor_balances():
    while True:
        users = db.users.find()
        for user in users:
            wallet_address = user["wallet"]
            private_key = user["private_key"]

            # Step 1: Check KASPER balance
            kasper_balance = wallet.get_balance(wallet_address)  # Updated to use synchronous method
            if kasper_balance > 0:
                logger.info(f"KASPER detected in {wallet_address}: {kasper_balance}")

                # Step 2: Check KAS balance for gas
                kas_balance = wallet.get_balance(wallet_address)
                if kas_balance < 20:
                    wallet.send_transaction(MAIN_WALLET_ADDRESS, wallet_address, 20 - kas_balance, MAIN_WALLET_PRIVATE_KEY)
                    logger.info(f"Transferred {20 - kas_balance} KAS to {wallet_address} for gas fees.")

                # Step 3: Send all KASPER to main wallet
                wallet.send_krc20_transaction(wallet_address, MAIN_WALLET_ADDRESS, kasper_balance, private_key)
                logger.info(f"Transferred {kasper_balance} KASPER from {wallet_address} to main wallet.")

                # Step 4: Return remaining KAS to main wallet
                remaining_kas = wallet.get_balance(wallet_address)
                if remaining_kas > 0:
                    wallet.send_transaction(wallet_address, MAIN_WALLET_ADDRESS, remaining_kas, private_key)
                    logger.info(f"Returned {remaining_kas} KAS to main wallet from {wallet_address}.")

        await asyncio.sleep(30)  # Repeat every 30 seconds

# Convert MP3 to OGG
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
async def elevenlabs_tts(text: str) -> bytes:
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
                json=payload
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error(f"Error in ElevenLabs TTS: {e}")
            return b""

# OpenAI Chat Completion
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

# Command Handlers
async def start_command(update, context):
    user_id = update.effective_user.id

    try:
        user = db.get_user(user_id)
        if not user:
            # Generate wallet address and private key
            wallet_address, private_key = wallet.create_wallet()
            if wallet_address and private_key:
                # Add user to the database
                db.add_user(user_id, credits=3, wallet=wallet_address, private_key=private_key)
                logger.info(f"New user registered: {user_id}")
                await update.message.reply_text(
                    f"👻 Welcome to Kasper AI! Your deposit wallet is: {wallet_address}. You have 3 free credits."
                )
            else:
                logger.error(f"Failed to generate wallet for user {user_id}")
                await update.message.reply_text("⚠️ Error generating wallet. Please try again later.")
        else:
            db.update_last_active(user_id)
            await update.message.reply_text(
                f"👋 Welcome back! You have {user['credits']} credits. Your deposit wallet is: {user['wallet']}."
            )
    except Exception as e:
        logger.error(f"Error in start_command for user {user_id}: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again later.")

async def handle_text_message(update, context):
    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    user = db.get_user(user_id)

    # Check if user exists and has credits
    if not user or user.get("credits", 0) <= 0:
        await update.message.reply_text(
            "❌ You have no credits remaining. Please use /topup to add more."
        )
        return

    try:
        # Notify user that the bot is processing their request
        await update.message.reply_text("👻 KASPER is thinking...")

        # Generate AI response and deduct credits only if successful
        ai_response = await generate_openai_response(user_text)
        if not ai_response:
            raise ValueError("AI response was empty.")

        mp3_audio = await elevenlabs_tts(ai_response)
        if not mp3_audio:
            raise ValueError("Audio generation failed.")

        ogg_audio = convert_mp3_to_ogg(mp3_audio)
        if not ogg_audio:
            raise ValueError("Audio conversion failed.")

        # Deduct 1 credit after successful API calls
        db.update_user_credits(user_id, user["credits"] - 1)
        logger.info(f"Deducted 1 credit from user {user_id}. Remaining credits: {user['credits'] - 1}.")

        # Send responses
        await update.message.reply_text(ai_response)
        await update.message.reply_voice(voice=ogg_audio)
    except Exception as e
