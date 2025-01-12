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
        """Run a Node.js command asynchronously with a timeout."""
        try:
            # Start the subprocess
            logger.info(f"Running Node.js command: {command} with args: {args}")
            process = await asyncio.create_subprocess_exec(
                "node", self.node_script_path, command, *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                # Wait for the process to complete with a timeout
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            except asyncio.TimeoutError:
                logger.error(f"Node.js command '{command}' timed out. Terminating process.")
                process.kill()
                await process.wait()
                return {"success": False, "error": "Subprocess timed out"}

            stdout = stdout.decode().strip()
            stderr = stderr.decode().strip()

            # Log outputs
            if stdout:
                logger.info(f"Node.js stdout for {command}: {stdout}")
            if stderr:
                logger.error(f"Node.js stderr for {command}: {stderr}")

            # Parse JSON output
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON output: {stdout}")
                return {"success": False, "error": "Invalid JSON in Node.js output"}

        except Exception as e:
            logger.error(f"Error running Node.js command '{command}': {e}")
            return {"success": False, "error": str(e)}

    async def create_wallet(self):
        """Create a new wallet."""
        logger.info("Creating a new wallet...")
        result = await self.run_node_command("createWallet")
        if result.get("success"):
            return {
                "success": True,
                "mnemonic": result.get("mnemonic"),
                "receiving_address": result.get("receivingAddress"),
                "change_address": result.get("changeAddress"),
                "private_key": result.get("xPrv"),
            }
        logger.error(f"Failed to create wallet: {result.get('error', 'Unknown error')}")
        return {"success": False, "error": result.get("error", "Unknown error")}
        
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
