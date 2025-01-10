
from pymongo import MongoClient

class DBManager:
    def __init__(self, db_uri="mongodb://localhost:27017/", db_name="kasper_ai_bot"):
        self.client = MongoClient(db_uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]

    def get_user(self, user_id):
        return self.users.find_one({"user_id": user_id})

    def add_user(self, user_id, credits=3, wallet=None):
        self.users.insert_one({
            "user_id": user_id,
            "credits": credits,
            "wallet": wallet
        })

    def update_user_credits(self, user_id, credits):
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"credits": credits}}
        )
