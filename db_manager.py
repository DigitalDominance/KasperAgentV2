# db_manager.py
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List
import logging
import os
from datetime import datetime
import asyncio
# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Define user schema using pydantic
class User(BaseModel):
    user_id: int
    credits: int
    wallet: str
    private_key: str
    mnemonic: str  # Required mnemonic for wallet recovery
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: Optional[datetime] = None
    processed_hashes: List[str] = Field(default_factory=list)  # To store processed transaction hashes


class DBManager:
    def __init__(self):
        try:
            # Retrieve MongoDB URI from environment variables
            mongo_uri = os.getenv("MONGODB_URI")
            if not mongo_uri:
                raise ValueError("MONGODB_URI is not set in the environment variables.")
            
            logger.info(f"Connecting to MongoDB at: {mongo_uri}")
            
            # Initialize AsyncIOMotorClient
            self.client = AsyncIOMotorClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=100,  # Adjust pool size based on your needs
                minPoolSize=5,
                connectTimeoutMS=10000,
                maxIdleTimeMS=300000
            )
            
            # Reference the database and the "users" collection
            self.db = self.client["kasperdb"]
            self.users = self.db["users"]

            # Ensure user_id is unique in the collection
            asyncio.get_event_loop().run_until_complete(self.ensure_indexes())
            
            logger.info("MongoDB connection pool initialized.")
        except Exception as e:
            logger.error(f"Error initializing DBManager: {e}")
            raise
    
    async def ensure_indexes(self):
        try:
            await self.users.create_index("user_id", unique=True)
            logger.info("Ensured unique index on user_id.")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

    async def add_user(self, user_id: int, credits: int, wallet: str, private_key: str, mnemonic: str):
        """Add a new user to the database."""
        try:
            user_data = User(
                user_id=user_id,
                credits=credits,
                wallet=wallet,
                private_key=private_key,
                mnemonic=mnemonic,
            ).dict()
            await self.users.insert_one(user_data)
            logger.info(f"User {user_id} added to the database.")
        except ValidationError as e:
            logger.error(f"Validation error while adding user: {e}")
        except errors.DuplicateKeyError:
            logger.warning(f"User {user_id} already exists in the database.")
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")

    async def get_user(self, user_id: int) -> Optional[dict]:
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

    async def add_processed_hash(self, user_id: int, hash_rev: str):
        """Add a processed transaction hash to the user's record."""
        try:
            result = await self.users.update_one(
                {"user_id": user_id},
                {"$addToSet": {"processed_hashes": hash_rev}},
            )
            if result.modified_count > 0:
                logger.info(f"Added processed hash for user {user_id}: {hash_rev}")
            else:
                logger.info(f"Processed hash {hash_rev} already exists for user {user_id}.")
        except Exception as e:
            logger.error(f"Error adding processed hash for user {user_id}: {e}")

    async def get_processed_hashes(self, user_id: int) -> List[str]:
        """Retrieve processed hashes for a user."""
        try:
            user = await self.users.find_one({"user_id": user_id}, {"processed_hashes": 1})
            return user.get("processed_hashes", []) if user else []
        except Exception as e:
            logger.error(f"Error retrieving processed hashes for user {user_id}: {e}")
            return []

    async def update_user_wallet(self, user_id: int, wallet: str, private_key: str, mnemonic: str):
        """Update a user's wallet information and mnemonic."""
        try:
            update_data = {
                "wallet": wallet,
                "private_key": private_key,
                "mnemonic": mnemonic,
                "last_active": datetime.utcnow(),
            }
            updated_user = await self.users.find_one_and_update(
                {"user_id": user_id},
                {"$set": update_data},
                return_document=ReturnDocument.AFTER,
            )
            if updated_user:
                logger.info(f"Updated wallet for user {user_id}.")
            else:
                logger.warning(f"User {user_id} not found for wallet update.")
        except Exception as e:
            logger.error(f"Error updating wallet for user {user_id}: {e}")

    async def update_user_credits(self, user_id: int, credits: int):
        """Update a user's credits."""
        try:
            updated_user = await self.users.find_one_and_update(
                {"user_id": user_id},
                {"$set": {"credits": credits, "last_active": datetime.utcnow()}},
                return_document=ReturnDocument.AFTER,
            )
            if updated_user:
                logger.info(f"Updated credits for user {user_id} to {credits}.")
            else:
                logger.warning(f"User {user_id} not found for updating credits.")
        except Exception as e:
            logger.error(f"Error updating credits for user {user_id}: {e}")

    async def update_last_active(self, user_id: int):
        """Update the last active timestamp for a user."""
        try:
            result = await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_active": datetime.utcnow()}},
            )
            if result.modified_count > 0:
                logger.info(f"Updated last_active timestamp for user {user_id}.")
            else:
                logger.warning(f"User {user_id} not found for updating last_active.")
        except Exception as e:
            logger.error(f"Error updating last_active for user {user_id}: {e}")

    async def delete_user(self, user_id: int):
        """Delete a user from the database."""
        try:
            result = await self.users.delete_one({"user_id": user_id})
            if result.deleted_count > 0:
                logger.info(f"User {user_id} deleted from the database.")
            else:
                logger.warning(f"User {user_id} not found in the database.")
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")

    def close_connection(self):
        """Close the MongoDB connection."""
        try:
            self.client.close()
            logger.info("MongoDB connection closed.")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
