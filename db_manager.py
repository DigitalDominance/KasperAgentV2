from pymongo import MongoClient
import os

class DBManager:
    def __init__(self):
        mongo_uri = os.getenv("MONGO_URI")
        self.client = MongoClient(mongo_uri)
        self.db = self.client["kasper_bot"]
        self.users = self.db["users"]

    def get_user(self, telegram_id):
        return self.users.find_one({"telegram_id": telegram_id})

    def create_user(self, telegram_id, wallet_address):
        user = {"telegram_id": telegram_id, "wallet_address": wallet_address, "credits": 0}
        self.users.insert_one(user)

    def update_credits(self, telegram_id, credits):
        self.users.update_one({"telegram_id": telegram_id}, {"$inc": {"credits": credits}})

    def get_credits(self, telegram_id):
        user = self.get_user(telegram_id)
        return user.get("credits", 0) if user else 0

    def set_wallet_address(self, telegram_id, wallet_address):
        self.users.update_one({"telegram_id": telegram_id}, {"$set": {"wallet_address": wallet_address}})
