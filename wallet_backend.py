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
    """Run a Node.js command asynchronously with improved logging."""
    try:
        # Log the command and arguments for better traceability
        logger.info(f"Running Node.js command: {command} with args: {args}")
        
        # Prepare payload for HTTP call
        payload = {"command": command, "args": args}

        # Send the command via HTTP to Node.js
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.node_script_path}/execute", json=payload, timeout=10)

        # Check response status
        if response.status_code != 200:
            logger.error(f"Node.js HTTP call failed with status {response.status_code}: {response.text}")
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}

        # Parse response JSON
        result = response.json()
        logger.info(f"Node.js response: {result}")
        return result

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
