# rate_limit.py
import time
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

# Dictionary to store user command timestamps
USER_COMMAND_LIMITS = {}

def rate_limit(max_per_minute):
    """
    Decorator to limit the number of times a user can invoke a command per minute.
    
    Args:
        max_per_minute (int): Maximum number of allowed commands per minute.
    
    Returns:
        function: The decorated function with rate limiting.
    """
    min_interval = 60.0 / max_per_minute

    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            current_time = time.time()
            last_time = USER_COMMAND_LIMITS.get(user_id, 0)

            if current_time - last_time < min_interval:
                await update.message.reply_text("⏳ Please wait a moment before trying again.")
                return

            USER_COMMAND_LIMITS[user_id] = current_time
            return await func(update, context, *args, **kwargs)

        return wrapper
    return decorator
