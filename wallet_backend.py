
import logging
from kaspa_client import KaspaClient

class WalletBackend:
    def __init__(self, rpc_url="http://127.0.0.1:16110"):
        self.client = KaspaClient(rpc_url=rpc_url)
        self.logger = logging.getLogger(__name__)

    def generate_wallet(self, user_id):
        try:
            wallet_address = self.client.create_new_address(label=f"User_{user_id}")
            self.logger.info(f"Generated wallet for user {user_id}: {wallet_address}")
            return wallet_address
        except Exception as e:
            self.logger.error(f"Error generating wallet for user {user_id}: {e}")
            return None

    def check_transactions(self, wallet_address):
        try:
            transactions = self.client.get_transactions(address=wallet_address)
            return transactions
        except Exception as e:
            self.logger.error(f"Error checking transactions for {wallet_address}: {e}")
            return []
