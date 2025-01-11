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

            # Parse and return JSON response
            if result.returncode == 0 and stdout:
                try:
                    parsed_data = json.loads(stdout)
                    return parsed_data
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error for {command}: {e}")
                    logger.error(f"Raw output causing error: {stdout}")
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
            try:
                # Parse wallet data
                parsed_data = {
                    "mnemonic": wallet_data["mnemonic"],
                    "receiving_address": wallet_data["receivingAddress"]["payload"],
                    "change_address": wallet_data["changeAddress"]["payload"],
                    "xprv": wallet_data["xPrv"]
                }
                logger.info(f"Wallet created successfully: {parsed_data}")
                return parsed_data
            except KeyError as e:
                logger.error(f"Missing key in wallet data: {e}")
                return {"success": False, "error": "Malformed wallet data"}
        else:
            logger.error(f"Failed to create wallet: {wallet_data.get('error')}")
            return {"success": False, "error": wallet_data.get('error')}

    def get_balance(self, address):
        """Get the balance of a specific address."""
        balance_data = self.run_node_command("getBalance", address)
        if balance_data.get("success"):
            try:
                # Parse balance data
                parsed_data = {
                    "address": balance_data["address"],
                    "balance": balance_data["balance"]
                }
                logger.info(f"Balance retrieved for {address}: {parsed_data['balance']} KAS")
                return parsed_data
            except KeyError as e:
                logger.error(f"Missing key in balance data: {e}")
                return {"success": False, "error": "Malformed balance data"}
        else:
            logger.error(f"Failed to retrieve balance for {address}: {balance_data.get('error')}")
            return {"success": False, "error": balance_data.get('error')}

    def send_transaction(self, from_address, to_address, amount, private_key):
        """Send a KAS transaction."""
        transaction_data = self.run_node_command(
            "sendTransaction", from_address, to_address, str(amount), private_key
        )
        if transaction_data.get("success"):
            try:
                # Parse transaction response
                parsed_data = {"txid": transaction_data["txid"]}
                logger.info(f"Transaction successful: {parsed_data}")
                return parsed_data
            except KeyError as e:
                logger.error(f"Missing key in transaction data: {e}")
                return {"success": False, "error": "Malformed transaction data"}
        else:
            logger.error(f"Failed to send transaction: {transaction_data.get('error')}")
            return {"success": False, "error": transaction_data.get('error')}

    def send_krc20_transaction(self, from_address, to_address, amount, private_key, token_symbol="KASPER"):
        """Send a KRC20 token transaction."""
        transaction_data = self.run_node_command(
            "sendKRC20Transaction", from_address, to_address, str(amount), private_key, token_symbol
        )
        if transaction_data.get("success"):
            try:
                # Parse KRC20 transaction response
                parsed_data = {"txid": transaction_data["txid"]}
                logger.info(f"KRC20 Transaction successful for {token_symbol}: {parsed_data}")
                return parsed_data
            except KeyError as e:
                logger.error(f"Missing key in KRC20 transaction data: {e}")
                return {"success": False, "error": "Malformed KRC20 transaction data"}
        else:
            logger.error(f"Failed to send KRC20 transaction: {transaction_data.get('error')}")
            return {"success": False, "error": transaction_data.get('error')}
