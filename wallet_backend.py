import subprocess
import json
import logging

logger = logging.getLogger(__name__)

class WalletBackend:
    def __init__(self, node_script_path="node_wasm_handler.js"):
        self.node_script_path = node_script_path

    def run_node_command(self, command, *args):
        """Run a Node.js script command and return the JSON result."""
        try:
            result = subprocess.run(
                ["node", self.node_script_path, command, *args],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                logger.debug(f"Node.js output for {command}: {output}")
                return json.loads(output)
            else:
                logger.error(f"Node.js error for {command}: {result.stderr.strip()}")
                return {"success": False, "error": result.stderr.strip()}
        except Exception as e:
            logger.error(f"Exception when running {command}: {e}")
            return {"success": False, "error": str(e)}

    def create_wallet(self):
        """Create a new wallet."""
        wallet_data = self.run_node_command("createWallet")
        if wallet_data.get("success"):
            logger.info(f"Wallet created: {wallet_data}")
        else:
            logger.error(f"Failed to create wallet: {wallet_data.get('error')}")
        return wallet_data

    def get_balance(self, address):
        """Get the balance for a given address."""
        balance_data = self.run_node_command("getBalance", address)
        if balance_data.get("success"):
            logger.info(f"Balance fetched for {address}: {balance_data['balance']} KAS")
        else:
            logger.error(f"Failed to fetch balance: {balance_data.get('error')}")
        return balance_data

    def send_transaction(self, from_address, to_address, amount, private_key):
        """Send a transaction."""
        tx_data = self.run_node_command(
            "sendTransaction", from_address, to_address, str(amount), private_key
        )
        if tx_data.get("success"):
            logger.info(f"Transaction successful: {tx_data}")
        else:
            logger.error(f"Transaction failed: {tx_data.get('error')}")
        return tx_data

    def send_krc20_transaction(self, from_address, to_address, amount, private_key, token_symbol="KASPER"):
        """Send a KRC20 token transaction."""
        krc20_data = self.run_node_command(
            "sendKRC20Transaction", from_address, to_address, str(amount), private_key, token_symbol
        )
        if krc20_data.get("success"):
            logger.info(f"KRC20 transaction successful: {krc20_data}")
        else:
            logger.error(f"KRC20 transaction failed: {krc20_data.get('error')}")
        return krc20_data
