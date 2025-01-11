import subprocess
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

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

            # Log Node.js outputs
            if stdout:
                logger.info(f"Node.js stdout for {command}: {stdout}")
            if stderr:
                logger.error(f"Node.js stderr for {command}: {stderr}")

            # Parse JSON output if available
            try:
                # Extract JSON if mixed with logs
                json_output = stdout[stdout.find("{"):]
                return json.loads(json_output)
            except (json.JSONDecodeError, ValueError):
                logger.error(f"Invalid JSON output: {stdout}")
                return {"success": False, "error": "Invalid JSON in Node.js output"}
        except Exception as e:
            logger.error(f"Error running {command}: {e}")
            return {"success": False, "error": str(e)}

    def create_wallet(self):
        """Create a new wallet."""
        wallet_data = self.run_node_command("createWallet")
        if wallet_data.get("success"):
            try:
                return {
                    "success": True,
                    "mnemonic": wallet_data["mnemonic"],
                    "receiving_address": wallet_data["receivingAddress"],
                    "change_address": wallet_data["changeAddress"],
                    "private_key": wallet_data["xPrv"],
                }
            except KeyError as e:
                logger.error(f"Malformed wallet data: {e}")
                return {"success": False, "error": "Incomplete wallet data"}
        else:
            return wallet_data

    def get_balance(self, address):
        """Get the balance of a specific address."""
        return self.run_node_command("getBalance", address)

    def send_transaction(self, from_address, to_address, amount, private_key):
        """Send a KAS transaction."""
        return self.run_node_command(
            "sendTransaction", from_address, to_address, str(amount), private_key
        )

    def send_krc20_transaction(self, from_address, to_address, amount, private_key, token_symbol="KASPER"):
        """Send a KRC20 token transaction."""
        return self.run_node_command(
            "sendKRC20Transaction", from_address, to_address, str(amount), private_key, token_symbol
        )

# Example usage
if __name__ == "__main__":
    backend = WalletBackend()

    # Example: Create a wallet
    wallet = backend.create_wallet()
    print(wallet)

    # Example: Get balance
    # balance = backend.get_balance("kaspa:example-address")
    # print(balance)

    # Example: Send a transaction
    # tx = backend.send_transaction("from_address", "to_address", 10, "private_key")
    # print(tx)
