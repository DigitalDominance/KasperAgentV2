import httpx
import logging
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class WalletBackend:
    def __init__(self, api_base_url="http://localhost:3000"):
        self.api_base_url = api_base_url

    async def run_node_command(self, command, *args):
        """Run a Node.js command via HTTP."""
        try:
            logger.info(f"Running Node.js command: {command} with args: {args}")
            payload = {"command": command, "args": args}

            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.api_base_url}/execute", json=payload, timeout=10)

            if response.status_code != 200:
                logger.error(f"Node.js HTTP call failed: {response.status_code} - {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}

            return response.json()
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
        logger.error(f"Failed to create wallet: {result.get('error')}")
        return {"success": False, "error": result.get("error", "Unknown error")}

    async def get_balance(self, address):
        """Get the balance of a specific address."""
        return await self.run_node_command("getBalance", address)

    async def send_kas_transaction(self, from_address, to_address, amount, private_key=None):
        """Send a KAS transaction."""
        return await self.run_node_command("sendTransaction", from_address, to_address, str(amount), private_key)
