import logging
import httpx
import json
import os

class WalletBackend:
    def __init__(self, kaspa_rpc_url="http://localhost:16110", kasplex_api_url="https://api.kasplex.org"):
        self.kaspa_rpc_url = kaspa_rpc_url
        self.kasplex_api_url = kasplex_api_url
        self.logger = logging.getLogger(__name__)
        self.main_wallet = os.getenv("MAIN_WALLET_ADDRESS", "")
        self.main_wallet_private_key = os.getenv("MAIN_WALLET_PRIVATE_KEY", "")

    async def rpc_request(self, method, params):
        """Make an RPC request to the Kaspa node."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(self.kaspa_rpc_url, json=payload)
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    self.logger.error(f"RPC error: {data['error']}")
                    return None
                return data.get("result")
        except Exception as e:
            self.logger.error(f"Error making RPC request: {e}")
            return None

    async def get_kas_balance(self, wallet_address):
        """Fetch KAS balance using RPC."""
        result = await self.rpc_request("getBalance", {"address": wallet_address})
        if result:
            balance = float(result.get("balance", 0))
            self.logger.info(f"KAS balance for {wallet_address}: {balance}")
            return balance
        return 0.0

    async def get_kasper_balance(self, wallet_address):
        """Fetch KRC20 (KASPER) balance using Kasplex API."""
        try:
            api_url = f"{self.kasplex_api_url}/v1/krc20/address/{wallet_address}/token/KASPER"
            async with httpx.AsyncClient() as client:
                response = await client.get(api_url)
                response.raise_for_status()
                data = response.json()
                if "result" in data and data["result"]:
                    balance = float(data["result"][0].get("balance", "0"))
                    self.logger.info(f"KASPER balance for {wallet_address}: {balance}")
                    return balance
                else:
                    self.logger.warning(f"No KASPER balance found for {wallet_address}.")
                    return 0.0
        except Exception as e:
            self.logger.error(f"Error fetching KASPER balance for {wallet_address}: {e}")
            return 0.0

    async def send_kas(self, from_address, to_address, amount, private_key):
        """Send KAS transaction using RPC."""
        params = {
            "fromAddress": from_address,
            "toAddress": to_address,
            "amount": amount,
            "privateKey": private_key
        }
        result = await self.rpc_request("createRawTransaction", params)
        if result:
            self.logger.info(f"Sent {amount} KAS from {from_address} to {to_address}.")
        else:
            self.logger.error(f"Failed to send {amount} KAS from {from_address} to {to_address}.")

    async def send_krc20(self, from_address, to_address, amount, private_key):
        """Send KRC20 (KASPER) transaction using RPC."""
        params = {
            "fromAddress": from_address,
            "toAddress": to_address,
            "amount": amount,
            "privateKey": private_key,
            "tokenSymbol": "KASPER"
        }
        result = await self.rpc_request("createRawTransaction", params)
        if result:
            self.logger.info(f"Sent {amount} KASPER from {from_address} to {to_address}.")
        else:
            self.logger.error(f"Failed to send {amount} KASPER from {from_address} to {to_address}.")

    async def generate_wallet(self):
        """Generate a new Kaspa wallet using RPC."""
        result = await self.rpc_request("createNewAddress", {})
        if result:
            address = result.get("address")
            private_key = result.get("privateKey")
            self.logger.info(f"Generated wallet: {address}")
            return address, private_key
        else:
            self.logger.error("Failed to generate wallet.")
            return None, None
