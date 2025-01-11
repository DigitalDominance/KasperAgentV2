import subprocess
import json
import logging

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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

            # Extract JSON from the output
            json_output = self.extract_json(stdout)
            if json_output:
                return json_output
            else:
                logger.error("Failed to decode JSON from Node.js output.")
                logger.error(stdout)
                return {"success": False, "error": "Invalid JSON in Node.js output"}
        except Exception as e:
            logger.error(f"Exception when running {command}: {e}")
            return {"success": False, "error": str(e)}

    def extract_json(self, raw_output):
        """Extract the valid JSON object from the raw output."""
        try:
            # Find and parse the last valid JSON object in the output
            lines = raw_output.splitlines()
            for line in reversed(lines):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
            return None
        except Exception as e:
            logger.error(f"Error extracting JSON: {e}")
            return None

    def create_wallet(self):
        """Create a new wallet."""
        wallet_data = self.run_node_command("createWallet")
        if wallet_data.get("success"):
            try:
                # Combine prefix and payload for the receiving address
                receiving_address_obj = wallet_data["receivingAddress"]
                receiving_address = f"{receiving_address_obj['prefix']}:{receiving_address_obj['payload']}"

                # Combine prefix and payload for the change address
                change_address_obj = wallet_data["changeAddress"]
                change_address = f"{change_address_obj['prefix']}:{change_address_obj['payload']}"

                # Prepare the parsed data
                parsed_data = {
                    "mnemonic": wallet_data["mnemonic"],
                    "receiving_address": receiving_address,
                    "change_address": change_address,
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
                balance = balance_data["balance"]
                parsed_data = {
                    "address": address,
                    "balance": balance,
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
                txid = transaction_data["txid"]
                logger.info(f"Transaction successful: {txid}")
                return {"success": True, "txid": txid}
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
                txid = transaction_data["txid"]
                logger.info(f"KRC20 Transaction successful for {token_symbol}: {txid}")
                return {"success": True, "txid": txid}
            except KeyError as e:
                logger.error(f"Missing key in KRC20 transaction data: {e}")
                return {"success": False, "error": "Malformed KRC20 transaction data"}
        else:
            logger.error(f"Failed to send KRC20 transaction: {transaction_data.get('error')}")
            return {"success": False, "error": transaction_data.get('error')}

# Example usage:
if __name__ == "__main__":
    backend = WalletBackend()
    wallet = backend.create_wallet()
    print(wallet)
