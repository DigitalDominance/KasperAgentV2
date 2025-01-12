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

    rate_per_credit = CREDIT_CONVERSION_RATE / (10 ** 8)  # Convert sompi to KASPER
    message = await update.message.reply_text(
        f"👻 Spook-tacular Top-Up!\n\n"
        f"🔑 Deposit Address: `{wallet_address}`\n"
        f"💸 Current Rate: 1 Credit = {rate_per_credit:.2f} KASPER\n\n"
        f"⏳ Remaining Time: 5:00\n\n"
        "✅ After depositing, finalize the process by using the `/endtopup` command."
    )

    # Cancel any previous scan
    if "scan_task" in context.chat_data:
        old_task = context.chat_data["scan_task"]
        if not old_task.done():
            old_task.cancel()

    # Start a new scan with countdown
    async def scan_deposits_with_countdown():
        try:
            async with httpx.AsyncClient() as client:
                end_time = datetime.utcnow() + timedelta(minutes=5)
                while datetime.utcnow() < end_time:
                    remaining_time = end_time - datetime.utcnow()
                    minutes, seconds = divmod(remaining_time.total_seconds(), 60)
                    countdown_text = f"⏳ Remaining Time: {int(minutes)}:{int(seconds):02d}"
                    
                    try:
                        # Edit the message to update the countdown
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=message.message_id,
                            text=(
                                f"👻 Spook-tacular Top-Up!\n\n"
                                f"🔑 Deposit Address: `{wallet_address}`\n"
                                f"💸 Current Rate: 1 Credit = {rate_per_credit:.2f} KASPER\n\n"
                                f"{countdown_text}\n\n"
                                "✅ After depositing, finalize the process by using the `/endtopup` command."
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception as edit_error:
                        logger.error(f"Error updating countdown message: {edit_error}")

                    # Check transactions during the scan
                    params = {"address": wallet_address, "tick": "KASPER"}
                    response = await client.get(f"{KRC20_API_BASE_URL}/oplist", params=params)
                    response.raise_for_status()
                    data = response.json()

                    for tx in data.get("result", []):
                        logger.info(f"KASPER transaction detected during scan: {tx}")

                    await asyncio.sleep(5)  # Update every 5 seconds

                # Timeout behavior
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message.message_id,
                    text=(
                        f"👻 *Spook-tacular Top-Up!*\n\n"
                        f"🔑 Deposit Address: `{wallet_address}`\n"
                        f"💸 Current Rate: 1 Credit = {rate_per_credit:.2f} KASPER\n\n"
                        "⏳ The top-up scan has timed out. Please use `/topup` to restart."
                    ),
                    parse_mode="Markdown",
                )
        except asyncio.CancelledError:
            logger.info("Scan task was canceled.")
        except Exception as e:
            logger.error(f"Error during top-up scan: {e}")

    context.chat_data["scan_task"] = asyncio.create_task(scan_deposits_with_countdown())



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

    # Cancel any active scan
    if "scan_task" in context.chat_data:
        scan_task = context.chat_data["scan_task"]
        if not scan_task.done():
            scan_task.cancel()
            await update.message.reply_text("⏳ Stopping the top-up scan...")

    # Process deposits
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{KRC20_API_BASE_URL}/oplist", params={"address": wallet_address, "tick": "KASPER"}
            )
            response.raise_for_status()
            data = response.json()

            # Calculate credits from new transactions
            total_credits = 0
            processed_hashes = db.get_processed_hashes(user_id)
            for tx in data.get("result", []):
                hash_rev = tx.get("hashRev")
                if hash_rev and hash_rev not in processed_hashes:
                    kasper_amount = int(tx.get("amt", 0))
                    credits = kasper_amount // CREDIT_CONVERSION_RATE
                    total_credits += credits

                    # Save processed hash
                    db.add_processed_hash(user_id, hash_rev)

            if total_credits > 0:
                # Update user's credits
                db.update_user_credits(user_id, user.get("credits", 0) + total_credits)
                await update.message.reply_text(
                    f"✅ *Spooky success!* Added {total_credits} credits to your account.\n\n"
                    "👻 Use /balance to see your updated credits!"
                )
            else:
                await update.message.reply_text("❌ No new KASPER deposits found.")
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

    logger.info("🚀 Starting Kasper AI Bot...")
    application.run_polling()


if __name__ == "__main__":
    main()
