# db_manager.py
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import errors
from datetime import datetime
import logging
import config
import asyncio

logger = logging.getLogger(__name__)

class DBManager:
    def __init__(self):
        try:
            mongo_uri = config.MONGODB_URI
            if not mongo_uri:
                raise ValueError("MONGODB_URI is not set in the environment variables.")
            
            logger.info(f"Connecting to MongoDB at: {mongo_uri}")
            
            self.client = AsyncIOMotorClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=100,
                minPoolSize=5,
                connectTimeoutMS=10000,
                maxIdleTimeMS=300000
            )
            self.db = self.client["kasperdb"]
            self.users = self.db["users"]
            logger.info("MongoDB connection pool initialized.")
        except errors.ServerSelectionTimeoutError as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}")
            raise

    async def init_db(self):
        """Initialize database indexes."""
        try:
            await self.users.create_index("user_id", unique=True)
            logger.info("Ensured unique index on user_id.")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
            raise

    async def get_user(self, user_id: int):
        """Retrieve a user from the database."""
        try:
            user = await self.users.find_one({"user_id": user_id})
            if user:
                logger.info(f"User {user_id} retrieved from the database.")
                return user
            logger.warning(f"User {user_id} not found in the database.")
            return None
        except Exception as e:
            logger.error(f"Error retrieving user {user_id}: {e}")
            return None

    async def add_user(self, user_id: int, credits: int, wallet: str, private_key: str):
        """Add a new user to the database."""
        try:
            user_data = {
                "user_id": user_id,
                "credits": credits,
                "wallet": wallet,
                "private_key": private_key,
                "created_at": datetime.utcnow(),
                "last_active": datetime.utcnow(),
                "processed_hashes": []
            }
            await self.users.insert_one(user_data)
            logger.info(f"Added user {user_id} to the database.")
        except errors.DuplicateKeyError:
            logger.warning(f"User {user_id} already exists in the database.")
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            raise

    async def add_processed_hash(self, user_id: int, hash_rev: str):
        """Add a processed transaction hash to the user's record."""
        try:
            result = await self.users.update_one(
                {"user_id": user_id},
                {"$addToSet": {"processed_hashes": hash_rev}}
            )
            if result.modified_count > 0:
                logger.info(f"Added processed hash for user {user_id}: {hash_rev}")
            else:
                logger.info(f"Processed hash {hash_rev} already exists for user {user_id}.")
        except Exception as e:
            logger.error(f"Error adding processed hash for user {user_id}: {e}")

    async def get_processed_hashes(self, user_id: int):
        """Retrieve processed hashes for a user."""
        try:
            user = await self.users.find_one({"user_id": user_id}, {"processed_hashes": 1})
            return user.get("processed_hashes", []) if user else []
        except Exception as e:
            logger.error(f"Error retrieving processed hashes for user {user_id}: {e}")
            return []
    
    async def update_user_credits(self, user_id: int, credits: int):
        """Update a user's credits."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"credits": credits, "last_active": datetime.utcnow()}}
            )
            logger.info(f"Updated credits for user {user_id} to {credits}.")
        except Exception as e:
            logger.error(f"Error updating credits for user {user_id}: {e}")
