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
            # Launch the Node.js subprocess
            process = await asyncio.create_subprocess_exec(
                "node", self.node_script_path, command, *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait for the process to complete
            stdout, stderr = await process.communicate()

            # Decode the output
            stdout = stdout.decode().strip()
            stderr = stderr.decode().strip()

            # Log outputs (asynchronously safe)
            if stdout:
                logger.info(f"[Node.js stdout - {command}]: {stdout}")
            if stderr:
                logger.error(f"[Node.js stderr - {command}]: {stderr}")

            # Parse and return JSON output
            try:
                json_output = json.loads(stdout)
                return json_output
            except json.JSONDecodeError:
                # Handle cases where logs might mix with JSON
                json_start = stdout.find("{")
                if json_start != -1:
                    try:
                        json_output = json.loads(stdout[json_start:])
                        return json_output
                    except json.JSONDecodeError:
                        pass
                logger.error(f"Invalid JSON output from {command}: {stdout}")
                return {"success": False, "error": "Invalid JSON in Node.js output"}

        except Exception as e:
            logger.error(f"Error running Node.js command '{command}': {e}")
            return {"success": False, "error": str(e)}

        finally:
            # Ensure the process is terminated
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def create_wallet(self):
        """Create a new wallet."""
        logger.info("Starting wallet creation...")
        wallet_data = await self.run_node_command("createWallet")
        if wallet_data.get("success"):
            # Validate required fields
            required_fields = ["mnemonic", "receivingAddress", "changeAddress", "xPrv"]
            missing_fields = [field for field in required_fields if field not in wallet_data]

            if missing_fields:
                logger.error(f"Missing fields in wallet creation response: {missing_fields}")
                return {"success": False, "error": "Incomplete wallet data"}

            # Return wallet details
            logger.info(f"Wallet successfully created: {wallet_data}")
            return {
                "success": True,
                "mnemonic": wallet_data["mnemonic"],
                "receiving_address": wallet_data["receivingAddress"],
                "change_address": wallet_data["changeAddress"],
                "private_key": wallet_data["xPrv"],
            }

        logger.error(f"Failed to create wallet: {wallet_data.get('error', 'Unknown error')}")
        return {"success": False, "error": wallet_data.get("error", "Unknown error")}

    async def get_balance(self, address):
        """Get the balance of a specific address."""
        logger.info(f"Fetching balance for address: {address}")
        return await self.run_node_command("getBalance", address)

    async def send_kas_transaction(self, from_address, to_address, amount, private_key=None, user_id=None):
        """Send a KAS transaction."""
        logger.info(f"Preparing to send KAS transaction from {from_address} to {to_address} (amount: {amount})")
        if private_key:
            response = await self.run_node_command("sendTransactionFromMainWallet", from_address, to_address, str(amount), private_key)
        elif user_id:
            response = await self.run_node_command("sendTransactionFromUserWallet", str(user_id), from_address, to_address, str(amount))
        else:
            logger.error("Either private_key or user_id must be provided for send_kas_transaction.")
            return {"success": False, "error": "Missing private_key or user_id"}

        if response.get("success"):
            logger.info(f"Transaction successful: {response}")
            return response
        else:
            logger.error(f"Failed to send KAS transaction: {response.get('error')}")
            return response

    async def send_krc20_transaction(self, from_address, to_address, amount, token_symbol="KASPER", private_key=None, user_id=None):
        """Send a KRC20 token transaction."""
        logger.info(f"Preparing to send KRC20 transaction from {from_address} to {to_address} (amount: {amount}, token: {token_symbol})")
        if user_id:
            response = await self.run_node_command(
                "sendKRC20Transaction", str(user_id), from_address, to_address, str(amount), token_symbol
            )
        elif private_key:
            response = await self.run_node_command(
                "sendKRC20Transaction", from_address, to_address, str(amount), private_key, token_symbol
            )
        else:
            logger.error("Either user_id or private_key must be provided for send_krc20_transaction.")
            return {"success": False, "error": "Missing user_id or private_key"}

        if response.get("success"):
            logger.info(f"KRC20 transaction successful: {response}")
            return response
        else:
            logger.error(f"Failed to send KRC20 transaction: {response.get('error')}")
            return response
