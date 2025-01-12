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


# /start Command Handler
async def start_command(update, context):
    user_id = update.effective_user.id
    try:
        user = db.get_user(user_id)
        if not user:
            wallet_data = wallet.create_wallet()
            if wallet_data.get("success"):
                wallet_address = wallet_data["receiving_address"]
                private_key = wallet_data["private_key"]
                mnemonic = wallet_data.get("mnemonic", "")
                db.add_user(user_id, credits=3, wallet=wallet_address, private_key=private_key, mnemonic=mnemonic)
                await update.message.reply_text(
                    f"👻 Welcome to Kasper AI! Use /topup to add credits to your account.\n"
                    f"Your wallet address: {wallet_address}"
                )
            else:
                await update.message.reply_text("⚠️ Failed to create a wallet. Please try again later.")
        else:
            total_credits = user.get("credits", 0)
            await update.message.reply_text(
                f"👻 Welcome back! You have {total_credits} credits in total. Use /topup to add more credits."
            )
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again later.")


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

    try:
        async with httpx.AsyncClient() as client:
            while context.chat_data.get("scan_active", False):
                try:
                    response = await client.get(f"{KRC20_API_BASE_URL}/op/{wallet_address}")
                    response.raise_for_status()
                    data = response.json()

                    for tx in data.get("result", []):
                        hash_rev = tx.get("hashRev")
                        if hash_rev and tx.get("tick") == "KASPER" and hash_rev not in db.get_processed_hashes(user_id):
                            kasper_amount = int(tx.get("amt", 0))
                            credits = kasper_amount // CREDIT_CONVERSION_RATE
                            db.add_processed_hash(user_id, hash_rev)
                            db.update_user_credits(user_id, user.get("credits", 0) + credits)
                            await update.message.reply_text(
                                f"✅ Detected deposit of {kasper_amount / (10 ** 8):.8f} KASPER.\n"
                                f"Added {credits} credits to your account."
                            )

                    if datetime.utcnow() >= context.chat_data["scan_timer"]:
                        context.chat_data["scan_active"] = False
                        await update.message.reply_text("⏳ The top-up scan has timed out. Please use `/topup` to restart.")
                except Exception as e:
                    logger.error(f"Error during top-up scan: {e}")

                await asyncio.sleep(10)
    except Exception as e:
        logger.error(f"Error in topup_command: {e}")
        await update.message.reply_text("❌ An error occurred during the top-up process. Please try again later.")


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

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{KRC20_API_BASE_URL}/op/{wallet_address}")
            response.raise_for_status()
            data = response.json()

            total_credits = 0
            for tx in data.get("result", []):
                hash_rev = tx.get("hashRev")
                if hash_rev and tx.get("tick") == "KASPER" and hash_rev not in db.get_processed_hashes(user_id):
                    kasper_amount = int(tx.get("amt", 0))
                    credits = kasper_amount // CREDIT_CONVERSION_RATE
                    total_credits += credits
                    db.add_processed_hash(user_id, hash_rev)

            if total_credits > 0:
                db.update_user_credits(user_id,
                user.get("credits", 0) + total_credits)
                await update.message.reply_text(
                    f"✅ Finalized top-up! Added {total_credits} credits to your account."
                )
            else:
                await update.message.reply_text("❌ No new KASPER deposits found.")
    except Exception as e:
        logger.error(f"Error in endtopup_command: {e}")
        await update.message.reply_text("❌ An error occurred during the finalization process. Please try again later.")


# /balance Command Handler
async def balance_command(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("❌ You need to /start first to create a wallet.")
        return

    total_credits = user.get("credits", 0)
    await update.message.reply_text(f"👻 You have {total_credits} credits available.")


# /text Command Handler (to handle direct AI responses)
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
        logger.error(f"Error in handle_text_message: {e}")
        await update.message.reply_text("❌ An error occurred while processing your message. Please try again later.")


# Main function
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Add all handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("topup", topup_command))
    application.add_handler(CommandHandler("endtopup", endtopup_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("🚀 Starting Kasper AI Bot...")
    application.run_polling()


if __name__ == "__main__":
    main()
