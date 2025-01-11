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
CREDIT_CONVERSION_RATE = 200  # 1 credit = 200 KASPER
KRC20_API_BASE_URL = os.getenv("KRC20_API_BASE_URL", "https://mainnet-api.kasplex.org/v1/krc20")

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

# /topup Command Handler
async def topup_command(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("❌ You need to /start first to create a wallet.")
        return

    wallet_address = user.get("wallet")
    if not wallet_address:
        await update.message.reply_text("❌ Your wallet is not set up. Please contact support.")
        return

    try:
        # Fetch KRC20 KASPER balance
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{KRC20_API_BASE_URL}/address/{wallet_address}/token/KASPER")
            response.raise_for_status()
            data = response.json()

        if data.get("result"):
            balance_info = data["result"][0]  # Assuming only one result for KASPER token
            kasper_balance = int(balance_info.get("balance", 0))

            if kasper_balance >= CREDIT_CONVERSION_RATE:
                credits_to_add = kasper_balance // CREDIT_CONVERSION_RATE
                db.update_user_credits(user_id, user.get("credits", 0) + credits_to_add)

                await update.message.reply_text(f"✅ {credits_to_add} credits added to your account!")
            else:
                await update.message.reply_text(f"⚠️ Your balance is too low for top-up. Minimum: {CREDIT_CONVERSION_RATE} KASPER.")
        else:
            await update.message.reply_text("⚠️ Unable to fetch balance. Please try again later.")
    except Exception as e:
        logger.error(f"Error in topup_command for user {user_id}: {e}")
        await update.message.reply_text("❌ Failed to process your top-up. Please try again later.")

# /balance Command Handler
async def balance_command(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("❌ You need to /start first to create a wallet.")
        return

    total_credits = user.get("credits", 0)
    await update.message.reply_text(f"👻 You have {total_credits} credits available.")

# Command Handlers
async def start_command(update, context):
    user_id = update.effective_user.id
    try:
        user = db.get_user(user_id)
        if not user:
            wallet_data = wallet.create_wallet()
            if wallet_data and wallet_data.get("success"):
                wallet_address = wallet_data.get("receiving_address")
                private_key = wallet_data.get("private_key")
                if not wallet_address or not private_key:
                    raise ValueError("Wallet data is incomplete")

                db.add_user(user_id, credits=3, wallet=wallet_address, private_key=private_key)
                await update.message.reply_text(
                    f"👻 Welcome to Kasper AI! Use /topup to add credits to your account."
                )
            else:
                await update.message.reply_text("⚠️ Failed to create a wallet. Please try again later.")
        else:
            total_credits = user.get("credits", 0)
            await update.message.reply_text(
                f"👻 Welcome back! You have {total_credits} credits in total. Use /topup to add more credits."
            )
    except Exception as e:
        logger.error(f"Error in start_command for user {user_id}: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again later.")

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

# Main function
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("topup", topup_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("🚀 Starting Kasper AI Bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
