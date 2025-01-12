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

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVEN_LABS_API_KEY = os.getenv("ELEVEN_LABS_API_KEY", "")
ELEVEN_LABS_VOICE_ID = os.getenv("ELEVEN_LABS_VOICE_ID", "0whGLe6wyQ2fwT9M40ZY")
CREDIT_CONVERSION_RATE = 200 * (10 ** 8)  # 1 credit = 200 KASPER (in sompi)
KRC20_API_BASE_URL = os.getenv("KRC20_API_BASE_URL", "https://api.kasplex.org/v1/krc20")

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize dependencies
db = DBManager()

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


# /start Command Handler
async def start_command(update, context):
    user_id = update.effective_user.id
    try:
        user = db.get_user(user_id)
        if not user:
            wallet_data = db.create_wallet()
            if wallet_data.get("success"):
                db.add_user(user_id, credits=3, **wallet_data)
                await update.message.reply_text(
                    "👻 *Welcome, brave spirit!* I am Kasper, your spectral guide.\n\n"
                    "🎁 *You start with 3 daily free credits!* Use /topup to acquire more ethereal power.\n\n"
                    "🌟 Let the adventure begin! Type /balance to check your credits."
                )
            else:
                await update.message.reply_text("⚠️ Failed to create a wallet. Please try again later.")
        else:
            total_credits = user.get("credits", 0)
            await update.message.reply_text(
                f"👻 Welcome back, spirit! You have {total_credits} credits remaining. Use /topup to gather more!"
            )
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again later.")


# /topup Command Handler
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

    countdown_time = 5 * 60  # 5 minutes in seconds
    countdown_message = await update.message.reply_text(
        f"👻 *The realm of credits awaits!* Each credit costs {CREDIT_CONVERSION_RATE // (10 ** 8)} KASPER.\n\n"
        f"📩 Deposit KASPER to this address: `{wallet_address}`\n\n"
        f"⏳ Time remaining: 5:00\n\n"
        "✅ Finalize the process with /endtopup once your deposit is complete."
    )

    context.chat_data["scan_active"] = True
    context.chat_data["scan_timer"] = datetime.utcnow() + timedelta(seconds=countdown_time)

    async with httpx.AsyncClient() as client:
        while context.chat_data.get("scan_active", False) and countdown_time > 0:
            try:
                # Update the countdown timer in the message
                minutes, seconds = divmod(countdown_time, 60)
                await countdown_message.edit_text(
                    f"👻 *The realm of credits awaits!* Each credit costs {CREDIT_CONVERSION_RATE // (10 ** 8)} KASPER.\n\n"
                    f"📩 Deposit KASPER to this address: `{wallet_address}`\n\n"
                    f"⏳ Time remaining: {minutes:02}:{seconds:02}\n\n"
                    "✅ Finalize the process with /endtopup once your deposit is complete."
                )
                countdown_time -= 10

                # Perform the KRC20 scan
                params = {"address": wallet_address, "tick": "KASPER"}
                response = await client.get(f"{KRC20_API_BASE_URL}/oplist", params=params)
                response.raise_for_status()
                data = response.json()

                for tx in data.get("result", []):
                    logger.info(f"KASPER transaction detected during scan: {tx}")

            except Exception as e:
                logger.error(f"Error during top-up scan: {e}")

            await asyncio.sleep(10)

        context.chat_data["scan_active"] = False

        if countdown_time <= 0:
            await countdown_message.edit_text(
                "⏳ *The top-up process has timed out.* Please use `/topup` to restart."
            )



# /endtopup Command Handler
async def endtopup_command(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("❌ You need to /start first to create a wallet.")
        return

    context.chat_data["scan_active"] = False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{KRC20_API_BASE_URL}/oplist", params={"address": user["wallet"], "tick": "KASPER"})
            response.raise_for_status()
            data = response.json()

            total_credits = 0
            processed_hashes = db.get_processed_hashes(user_id)
            for tx in data.get("result", []):
                if tx["hashRev"] not in processed_hashes:
                    db.add_processed_hash(user_id, tx["hashRev"])
                    total_credits += int(tx["amt"]) // CREDIT_CONVERSION_RATE

            db.update_user_credits(user_id, user.get("credits", 0) + total_credits)

            await update.message.reply_text(
                f"👻 *Spectacular!* {total_credits} credits have been added to your ethereal pool. Use /balance to see your new total!"
            )
    except Exception as e:
        logger.error(f"Error in endtopup_command: {e}")
        await update.message.reply_text("❌ An error occurred during the top-up process. Please try again later.")


# /balance Command Handler
async def balance_command(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("❌ You need to /start first to create a wallet.")
        return

    await update.message.reply_text(f"👻 You have {user.get('credits', 0)} credits remaining.")


# Main function
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("topup", topup_command))
    application.add_handler(CommandHandler("endtopup", endtopup_command))
    application.add_handler(CommandHandler("balance", balance_command))

    logger.info("🚀 Starting Kasper AI Bot...")
    application.run_polling()


if __name__ == "__main__":
    main()
