
import logging
import httpx
import asyncio
from typing import Optional

class WalletBackend:
    def __init__(self, 
                 kaspa_rpc_url="http://localhost:16110",
                 kasplex_api_url="https://api.kasplex.org",
                 rpc_timeout=10,
                 rpc_max_retries=3,
                 rpc_retry_delay=2):
        self.kaspa_rpc_url = kaspa_rpc_url
        self.kasplex_api_url = kasplex_api_url
        self.rpc_timeout = rpc_timeout
        self.rpc_max_retries = rpc_max_retries
        self.rpc_retry_delay = rpc_retry_delay
        self.logger = logging.getLogger(__name__)

    async def rpc_request(self, method: str, params: Optional[dict] = None):
        """Perform an RPC request to the Kaspa node with retries."""
        if params is None:
            params = {}

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }

        for attempt in range(1, self.rpc_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.rpc_timeout) as client:
                    response = await client.post(self.kaspa_rpc_url, json=payload)
                    response.raise_for_status()
                    result = response.json()
                    if "error" in result:
                        self.logger.error(f"RPC error: {result['error']}")
                        return None
                    return result.get("result")
            except httpx.RequestError as e:
                self.logger.warning(f"Attempt {attempt}/{self.rpc_max_retries}: RPC request error: {e}")
                if attempt < self.rpc_max_retries:
                    await asyncio.sleep(self.rpc_retry_delay)
                else:
                    self.logger.error(f"RPC request failed after {self.rpc_max_retries} attempts.")
            except Exception as e:
                self.logger.error(f"Unexpected error during RPC request: {e}")
                break
        return None

    async def get_kas_balance(self, wallet_address):
        """Fetch KAS balance using RPC."""
        try:
            result = await self.rpc_request("getBalance", {"address": wallet_address})
            if result:
                balance = float(result.get("balance", 0))
                self.logger.info(f"KAS balance for {wallet_address}: {balance}")
                return balance
            return 0.0
        except Exception as e:
            self.logger.error(f"Error fetching KAS balance for {wallet_address}: {e}")
            return 0.0

    async def get_kasper_balance(self, wallet_address):
        """Fetch KRC20 (KASPER) balance using the Kasplex API."""
        try:
            api_url = f"{self.kasplex_api_url}/v1/krc20/address/{wallet_address}/token/KASPER"
            async with httpx.AsyncClient() as client:
                response = await client.get(api_url)
                response.raise_for_status()
                data = response.json()
                if "result" in data and data["result"]:
                    balance = float(data["result"][0].get("balance", 0))
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
        try:
            params = {
                "fromAddress": from_address,
                "toAddress": to_address,
                "amount": amount,
                "privateKey": private_key
            }
            result = await self.rpc_request("sendTransaction", params)
            if result:
                self.logger.info(f"Sent {amount} KAS from {from_address} to {to_address}.")
                return result
            self.logger.error(f"Failed to send {amount} KAS from {from_address} to {to_address}.")
            return None
        except Exception as e:
            self.logger.error(f"Error in send_kas: {e}")
            return None

    async def send_krc20(self, from_address, to_address, amount, private_key):
        """Send KRC20 (KASPER) transaction using RPC."""
        try:
            params = {
                "fromAddress": from_address,
                "toAddress": to_address,
                "amount": amount,
                "privateKey": private_key,
                "tokenSymbol": "KASPER"
            }
            result = await self.rpc_request("sendTransaction", params)
            if result:
                self.logger.info(f"Sent {amount} KASPER from {from_address} to {to_address}.")
                return result
            self.logger.error(f"Failed to send {amount} KASPER from {from_address} to {to_address}.")
            return None
        except Exception as e:
            self.logger.error(f"Error in send_krc20: {e}")
            return None

    async def generate_wallet(self):
        """Generate a new wallet address using RPC."""
        try:
            result = await self.rpc_request("generateNewAddress")
            if result:
                address = result.get("address")
                private_key = result.get("privateKey")
                self.logger.info(f"Generated wallet address: {address}")
                return address, private_key
            self.logger.error("Failed to generate wallet address.")
            return None, None
        except Exception as e:
            self.logger.error(f"Error in generate_wallet: {e}")
            return None, None
