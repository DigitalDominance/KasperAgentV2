import asyncio
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class WalletBackend:
    def __init__(self, node_script_path="node_wasm_handler.js"):
        self.node_script_path = node_script_path

    async def run_node_command(self, command, *args):
        """Run a Node.js command asynchronously and handle the response."""
        try:
            process = await asyncio.create_subprocess_exec(
                "node",
                self.node_script_path,
                command,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            stdout = stdout.decode().strip()
            stderr = stderr.decode().strip()

            # Log Node.js outputs
            if stdout:
                logger.info(f"Node.js stdout for {command}: {stdout}")
            if stderr:
                logger.error(f"Node.js stderr for {command}: {stderr}")

            # Parse JSON output
            try:
                json_output = json.loads(stdout)
                return json_output
            except json.JSONDecodeError:
                # Handle cases where the output may contain non-JSON logs
                json_start = stdout.find("{")
                if json_start != -1:
                    try:
                        json_output = json.loads(stdout[json_start:])
                        return json_output
                    except json.JSONDecodeError:
                        pass
                logger.error(f"Invalid JSON output: {stdout}")
                return {"success": False, "error": "Invalid JSON in Node.js output"}
        except Exception as e:
            logger.error(f"Error running {command}: {e}")
            return {"success": False, "error": str(e)}

    async def create_wallet(self):
        """Create a new wallet asynchronously."""
        wallet_data = await self.run_node_command("createWallet")
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

    async def get_balance(self, address):
        """Get the balance of a specific address asynchronously."""
        return await self.run_node_command("getBalance", address)

    async def send_kas_transaction(self, from_address, to_address, amount, private_key=None, user_id=None):
        """Send a KAS transaction asynchronously."""
        if private_key:
            # Main wallet transaction
            response = await self.run_node_command("sendTransactionFromMainWallet", from_address, to_address, str(amount), private_key)
        elif user_id:
            # User wallet transaction
            response = await self.run_node_command("sendTransactionFromUserWallet", str(user_id), from_address, to_address, str(amount))
        else:
            logger.error("Either private_key or user_id must be provided for send_kas_transaction.")
            return {"success": False, "error": "Missing private_key or user_id"}

        if response.get("success"):
            return response
        else:
            logger.error(f"Failed to send KAS transaction: {response.get('error')}")
            return response

    async def send_krc20_transaction(self, from_address, to_address, amount, token_symbol="KASPER", private_key=None, user_id=None):
        """Send a KRC20 token transaction asynchronously."""
        if user_id:
            # Retrieve private key for the user from Node.js
            response = await self.run_node_command(
                "sendKRC20Transaction", str(user_id), from_address, to_address, str(amount), token_symbol
            )
        elif private_key:
            # Use provided private key (e.g., from environment variables)
            response = await self.run_node_command(
                "sendKRC20Transaction", from_address, to_address, str(amount), private_key, token_symbol
            )
        else:
            logger.error("Either user_id or private_key must be provided for send_krc20_transaction.")
            return {"success": False, "error": "Missing user_id or private_key"}

        if response.get("success"):
            return response
        else:
            logger.error(f"Failed to send KRC20 transaction: {response.get('error')}")
            return response

# Example usage
if __name__ == "__main__":
    async def main():
        backend = WalletBackend()

        # Example: Create a wallet
        wallet = await backend.create_wallet()
        print(wallet)

        # Example: Get balance
        # balance = await backend.get_balance("kaspa:example-address")
        # print(balance)

        # Example: Send a transaction
        # tx = await backend.send_kas_transaction("from_address", "to_address", 10, "private_key")
        # print(tx)

    asyncio.run(main())
