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
CREDIT_CONVERSION_RATE = 200 * (10 ** 8)  # 1 credit = 200 KASPER (in sompi)
KRC20_API_BASE_URL = os.getenv("KRC20_API_BASE_URL", "https://api.kasplex.org/v1/krc20")
MAIN_WALLET_ADDRESS = os.getenv("MAIN_WALLET_ADDRESS", "")
MAIN_WALLET_PRIVATE_KEY = os.getenv("MAIN_WALLET_PRIVATE_KEY", "")

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

    await update.message.reply_text(
        f"👻 Please deposit KASPER to this address: {wallet_address}.\n\n"
        "✅ After depositing, finalize the process by using the `/endtopup` command.\n\n"
        "⏳ Note: The top-up scan will automatically stop after 5 minutes."
    )

    context.chat_data["scan_active"] = True
    context.chat_data["scan_timer"] = datetime.utcnow() + timedelta(minutes=5)

    async with httpx.AsyncClient() as client:
        while context.chat_data.get("scan_active", False):
            try:
                response = await client.get(f"{KRC20_API_BASE_URL}/op/{wallet_address}")
                response.raise_for_status()
                data = response.json()

                for tx in data.get("result", []):
                    if tx.get("tick") == "KASPER":
                        logger.info(f"KASPER transaction detected: {tx}")

                if datetime.utcnow() >= context.chat_data["scan_timer"]:
                    context.chat_data["scan_active"] = False
                    await update.message.reply_text("⏳ The top-up scan has timed out. Please use `/topup` to restart.")

            except Exception as e:
                logger.error(f"Error during top-up scan: {e}")

            await asyncio.sleep(10)

# /endtopup Command Handler
async def endtopup_command(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("❌ You need to /start first to create a wallet.")
        return

    wallet_address = user.get("wallet")
    if not wallet_address:
        await update.message.reply_text("❌ Your wallet is not set up. Please contact support.")
        return

    context.chat_data["scan_active"] = False
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{KRC20_API_BASE_URL}/op/{wallet_address}")
            response.raise_for_status()
            data = response.json()

            total_credits = 0
            for tx in data.get("result", []):
                if tx.get("tick") == "KASPER":
                    kasper_amount = int(tx.get("amt", 0))
                    credits = kasper_amount // CREDIT_CONVERSION_RATE
                    total_credits += credits

            if total_credits > 0:
                db.update_user_credits(user_id, user.get("credits", 0) + total_credits)
                await update.message.reply_text(
                    f"✅ Top-up successful! Added {total_credits} credits to your account."
                )
            else:
                await update.message.reply_text("❌ No KASPER deposits found.")
        except Exception as e:
            logger.error(f"Error in endtopup_command: {e}")
            await update.message.reply_text("❌ An error occurred during the top-up process. Please try again later.")

# Main function
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("topup", topup_command))
    application.add_handler(CommandHandler("endtopup", endtopup_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("🚀 Starting Kasper AI Bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
