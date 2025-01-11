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

        # Extract JSON from stdout
            json_data = self.extract_json(stdout)
            if json_data:
                return json_data
            else:
                logger.error("Failed to extract JSON. Raw output:")
                logger.error(stdout)
                return {"success": False, "error": "Failed to extract JSON from Node.js output"}
        except Exception as e:
            logger.error(f"Exception when running {command}: {e}")
            return {"success": False, "error": str(e)}
    def extract_json(self, raw_output):
        try:
        # Split the output into lines
        lines = raw_output.splitlines()

        # Iterate through lines to find JSON
        for line in lines:
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                return json.loads(line)  # Parse the JSON line
        logger.error("No valid JSON object found in the Node.js output.")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {e}")
        logger.error(f"Raw output causing error: {raw_output}")
        return None

    def create_wallet(self):
   
    wallet_data = self.run_node_command("createWallet")
    if wallet_data.get("success"):
        try:
            # Combine prefix and payload for the receiving address
            receiving_address_obj = wallet_data["receivingAddress"]
            receiving_address = f"{receiving_address_obj['prefix']}:{receiving_address_obj['payload']}"
            
            # Prepare the final output
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
