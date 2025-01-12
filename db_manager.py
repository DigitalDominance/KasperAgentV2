from pymongo import MongoClient, errors
from pymongo.collection import ReturnDocument
from pydantic import BaseModel, Field
from typing import Optional, List
import logging
import os
from datetime import datetime

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
            mongo_uri = os.getenv("MONGODB_URI")
            if not mongo_uri:
                raise ValueError("MONGODB_URI is not set in the environment variables.")
            logging.info(f"Connecting to MongoDB at: {mongo_uri}")
            self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client["kasperdb"]
            self.users = self.db["users"]
            self.users.create_index("user_id", unique=True)
        except errors.ServerSelectionTimeoutError as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}")
            raise

    def add_user(self, user_id: int, credits: int, wallet: str, private_key: str, mnemonic: str):
        """Add a new user to the database."""
        try:
            user_data = User(
                user_id=user_id,
                credits=credits,
                wallet=wallet,
                private_key=private_key,
                mnemonic=mnemonic,
            ).dict()
            self.users.insert_one(user_data)
            logger.info(f"User {user_id} added to the database.")
        except ValidationError as e:
            logger.error(f"Validation error while adding user: {e}")
        except errors.DuplicateKeyError:
            logger.warning(f"User {user_id} already exists in the database.")
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")

    def get_user(self, user_id: int) -> Optional[dict]:
        """Retrieve a user from the database."""
        try:
            user = self.users.find_one({"user_id": user_id})
            if user:
                logger.info(f"User {user_id} retrieved from the database.")
                return user
            logger.warning(f"User {user_id} not found in the database.")
            return None
        except Exception as e:
            logger.error(f"Error retrieving user {user_id}: {e}")
            return None

    def add_processed_hash(self, user_id: int, hash_rev: str):
        """Add a processed transaction hash to the user's record."""
        try:
            self.users.update_one(
                {"user_id": user_id},
                {"$addToSet": {"processed_hashes": hash_rev}},
            )
            logger.info(f"Added processed hash for user {user_id}: {hash_rev}")
        except Exception as e:
            logger.error(f"Error adding processed hash for user {user_id}: {e}")

    def get_processed_hashes(self, user_id: int) -> List[str]:
        """Retrieve processed hashes for a user."""
        try:
            user = self.users.find_one({"user_id": user_id}, {"processed_hashes": 1})
            return user.get("processed_hashes", []) if user else []
        except Exception as e:
            logger.error(f"Error retrieving processed hashes for user {user_id}: {e}")
            return []

    def update_user_wallet(self, user_id: int, wallet: str, private_key: str, mnemonic: str):
        """Update a user's wallet information and mnemonic."""
        try:
            update_data = {
                "wallet": wallet,
                "private_key": private_key,
                "mnemonic": mnemonic,
                "last_active": datetime.utcnow(),
            }
            updated_user = self.users.find_one_and_update(
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

    def update_user_credits(self, user_id: int, credits: int):
        """Update a user's credits."""
        try:
            updated_user = self.users.find_one_and_update(
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

    def update_last_active(self, user_id: int):
        """Update the last active timestamp for a user."""
        try:
            self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_active": datetime.utcnow()}},
            )
            logger.info(f"Updated last_active timestamp for user {user_id}.")
        except Exception as e:
            logger.error(f"Error updating last_active for user {user_id}: {e}")

    def delete_user(self, user_id: int):
        """Delete a user from the database."""
        try:
            result = self.users.delete_one({"user_id": user_id})
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
