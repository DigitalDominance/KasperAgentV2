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
        """Run a Node.js command and return its JSON output."""
        try:
            result = subprocess.run(
                ["node", self.node_script_path, command, *args],
                capture_output=True,
                text=True,
            )
            # Assume stdout contains valid JSON
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from Node.js command '{command}'. Output: {result.stdout}")
            return {"success": False, "error": "Invalid JSON in Node.js output"}
        except Exception as e:
            logger.error(f"Error while running Node.js command '{command}': {e}")
            return {"success": False, "error": str(e)}

def create_wallet(self):
    """Create a new wallet."""
    wallet_data = self.run_node_command("createWallet")
    if wallet_data.get("success"):
        # Validate necessary fields
        receiving_address = wallet_data.get("receivingAddress")
        xprv = wallet_data.get("xPrv")

        if receiving_address and "prefix" in receiving_address and "payload" in receiving_address and xprv:
            receiving_address_full = f"{receiving_address['prefix']}:{receiving_address['payload']}"
            return {
                "success": True,
                "mnemonic": wallet_data["mnemonic"],
                "receiving_address": receiving_address_full,
                "change_address": f"{wallet_data['changeAddress']['prefix']}:{wallet_data['changeAddress']['payload']}",
                "private_key": xprv,
            }
        else:
            logger.error(f"Incomplete wallet data: {wallet_data}")
            return {"success": False, "error": "Incomplete wallet data"}
    else:
        logger.error(f"Failed to create wallet: {wallet_data}")
        return {"success": False, "error": wallet_data.get("error", "Unknown error")}


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
