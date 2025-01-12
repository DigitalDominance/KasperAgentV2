import httpx
import logging
import asyncio
import os
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class WalletBackend:
    def __init__(self, api_base_url=None, api_key=None): 
        self.api_base_url = api_base_url or os.getenv("NODE_API_BASE_URL")
        self.api_key = api_key or os.getenv("API_KEY")

    async def run_node_command(self, command, *args):
        """Send a command to the Node.js backend."""
        payload = {"command": command, "args": args}
        headers = {
            "x-api-key": self.api_key  # Include API key in headers
        }
        try:
            logger.info(f"Sending payload to Node.js: {payload}")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base_url}/execute",
                    json=payload,
                    headers=headers,  # Pass headers to the request
                    timeout=30
                )
            logger.info(f"Response from Node.js: {response.status_code} - {response.text}")
            response.raise_for_status()
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
        logger.info(f"Fetching balance for address: {address}")
        return await self.run_node_command("getBalance", address)
