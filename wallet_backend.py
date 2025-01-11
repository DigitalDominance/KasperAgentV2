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

            # Extract JSON response
            json_data = self.extract_json(stdout)
            if json_data:
                return json_data
            else:
                return {"success": False, "error": "Invalid JSON in Node.js output"}
        except Exception as e:
            logger.error(f"Exception when running {command}: {e}")
            return {"success": False, "error": str(e)}

    def extract_json(self, raw_output):
    """Extract the valid JSON object from raw Node.js output."""
    try:
        # Identify the JSON block within the output
        start_idx = raw_output.find("{")
        end_idx = raw_output.rfind("}")
        
        if start_idx != -1 and end_idx != -1:
            json_string = raw_output[start_idx:end_idx + 1]
            return json.loads(json_string)
        else:
            logger.error("No valid JSON object found in the Node.js output.")
            logger.error(f"Raw output causing error: {raw_output}")
            return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {e}")
        logger.error(f"Raw output causing error: {raw_output}")
        return None


    def create_wallet(self):
        """Create a new wallet."""
        wallet_data = self.run_node_command("createWallet")
        if wallet_data.get("success"):
            try:
                # Construct the receiving address
                receiving_address = (
                    f"{wallet_data['receivingAddress']['prefix']}:{wallet_data['receivingAddress']['payload']}"
                )
                # Prepare the parsed data
                parsed_data = {
                    "mnemonic": wallet_data["mnemonic"],
                    "receiving_address": receiving_address,
                    "private_key": wallet_data["xPrv"],
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
                parsed_data = {
                    "address": address,
                    "balance": balance_data["balance"],
                }
                logger.info(f"Balance retrieved: {parsed_data}")
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
                return {"success": True, "txid": transaction_data["txid"]}
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
                return {"success": True, "txid": transaction_data["txid"]}
            except KeyError as e:
                logger.error(f"Missing key in KRC20 transaction data: {e}")
                return {"success": False, "error": "Malformed KRC20 transaction data"}
        else:
            logger.error(f"Failed to send KRC20 transaction: {transaction_data.get('error')}")
            return {"success": False, "error": transaction_data.get('error')}

# Example usage
if __name__ == "__main__":
    wallet_backend = WalletBackend()
    wallet_data = wallet_backend.create_wallet()
    print(wallet_data)
