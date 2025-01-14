from pymongo import MongoClient
import os
from datetime import datetime

class DBManager:
    def __init__(self):
        mongo_uri = os.getenv("MONGO_URI")
        self.client = MongoClient(mongo_uri)
        self.db = self.client["kasper_bot"]
        self.users = self.db["users"]

    def get_user(self, telegram_id):
        """Retrieve a user by their Telegram ID."""
        return self.users.find_one({"telegram_id": telegram_id})
        
    def is_transaction_processed(self, hash_rev: str) -> bool:
        """
        Check if a transaction with the given hashRev is already processed.
        """
        return self.db["transactions"].find_one({"hashRev": hash_rev}) is not None

    def save_transaction(self, hash_rev: str, amount: float):
        """
        Save a new transaction to the database.
        """
        transaction = {"hashRev": hash_rev, "amount": amount, "timestamp": datetime.utcnow()}
        self.db["transactions"].insert_one(transaction)
        
    def create_user(self, telegram_id, wallet_address, private_key, mnemonic, credits=0):
        """
        Create a new user in the database with their wallet information.

        Args:
            telegram_id (int): Telegram user ID.
            wallet_address (str): The wallet address associated with the user.
            private_key (str): The private key for the user's wallet.
            mnemonic (str): The mnemonic phrase for the user's wallet.
            credits (int, optional): Initial credits for the user. Defaults to 0.
        """
        user = {
            "telegram_id": telegram_id,
            "wallet_address": wallet_address,
            "private_key": private_key,
            "mnemonic": mnemonic,
            "credits": credits,
            "created_at": datetime.utcnow(),
        }
        self.users.insert_one(user)

    def transaction_exists(self, hashRev: str) -> bool:
        """Check if a transaction already exists in the database."""
        return self.transactions.find_one({"hashRev": hashRev}) is not None

    def add_transaction(self, transaction: dict):
        """Add a new transaction to the database."""
        self.transactions.insert_one(transaction)

    def update_credits(self, telegram_id: int, credits: int):
        """Update the user's credit balance."""
        self.users.update_one({"telegram_id": telegram_id}, {"$inc": {"credits": credits}})

    def get_credits(self, telegram_id):
        """
        Retrieve the number of credits for a user.

        Args:
            telegram_id (int): Telegram user ID.

        Returns:
            int: Number of credits the user has, or 0 if the user does not exist.
        """
        user = self.get_user(telegram_id)
        return user.get("credits", 0) if user else 0
