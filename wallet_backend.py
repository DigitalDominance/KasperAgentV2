import subprocess
import json
import logging

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class WalletBackend:
    def __init__(self, node_script_path="node_wasm_handler.js"):
        self.node_script_path = node_script_path

    def run_node_command(self, command, *args):
        """Run a Node.js command and handle the response."""
        try:
            result = subprocess.run(
                ["node", self.node_script_path, command, *args],
                capture_output=True,
                text=True,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            # Log stdout and stderr for debugging
            if stdout:
                logger.info(f"Node.js stdout for {command}: {stdout}")
            if stderr:
                logger.error(f"Node.js stderr for {command}: {stderr}")

            # Handle response
            if result.returncode == 0:
                try:
                    parsed_data = json.loads(stdout)
                    logger.info(f"Parsed JSON response for {command}: {parsed_data}")
                    return parsed_data
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error for {command}: {e}")
                    return {"success": False, "error": "Invalid JSON response"}
            else:
                return {"success": False, "error": stderr or "Unknown error occurred"}
        except Exception as e:
            logger.error(f"Exception when running {command}: {e}")
            return {"success": False, "error": str(e)}

    def create_wallet(self):
        """Create a new wallet."""
        wallet_data = self.run_node_command("createWallet")
        if wallet_data.get("success"):
            logger.info(f"Wallet created successfully: {wallet_data}")
        else:
            logger.error(f"Failed to create wallet: {wallet_data.get('error')}")
        return wallet_data

    def get_balance(self, address):
        """Get the balance of a specific address."""
        balance_data = self.run_node_command("getBalance", address)
        if balance_data.get("success"):
            logger.info(f"Balance retrieved for {address}: {balance_data['balance']} KAS")
        else:
            logger.error(f"Failed to retrieve balance for {address}: {balance_data.get('error')}")
        return balance_data

    def send_transaction(self, from_address, to_address, amount, private_key):
        """Send a KAS transaction."""
        transaction_data = self.run_node_command(
            "sendTransaction", from_address, to_address, str(amount), private_key
        )
        if transaction_data.get("success"):
            logger.info(f"Transaction successful: {transaction_data}")
        else:
            logger.error(f"Failed to send transaction: {transaction_data.get('error')}")
        return transaction_data

    def send_krc20_transaction(self, from_address, to_address, amount, private_key, token_symbol="KASPER"):
        """Send a KRC20 token transaction."""
        transaction_data = self.run_node_command(
            "sendKRC20Transaction", from_address, to_address, str(amount), private_key, token_symbol
        )
        if transaction_data.get("success"):
            logger.info(f"KRC20 Transaction successful for {token_symbol}: {transaction_data}")
        else:
            logger.error(f"Failed to send KRC20 transaction: {transaction_data.get('error')}")
        return transaction_data
