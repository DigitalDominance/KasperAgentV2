
import logging
import asyncio
from typing import Optional
from wasm import RpcClient, Resolver


class WalletBackend:
    def __init__(self,
                 network_id="mainnet",
                 kasplex_api_url="https://api.kasplex.org"):
        self.kasplex_api_url = kasplex_api_url
        self.logger = logging.getLogger(__name__)
        self.rpc = RpcClient({
            "resolver": Resolver(),
            "networkId": network_id,
        })
        self.loop = asyncio.get_event_loop()

    async def connect_rpc(self):
        """Connect to the Kaspa node using the resolver."""
        try:
            self.rpc.addEventListener("connect", lambda _: self.logger.info("Connected to Kaspa RPC"))
            self.rpc.addEventListener("disconnect", lambda _: self.logger.warning("Disconnected from Kaspa RPC"))
            await self.rpc.connect()
            self.logger.info("RPC connection established.")
        except Exception as e:
            self.logger.error(f"Error connecting to Kaspa RPC: {e}")

    async def disconnect_rpc(self):
        """Disconnect from the Kaspa node."""
        try:
            await self.rpc.disconnect()
            self.logger.info("Disconnected from Kaspa RPC.")
        except Exception as e:
            self.logger.error(f"Error disconnecting from Kaspa RPC: {e}")

    async def get_kas_balance(self, wallet_address: str) -> float:
        """Fetch KAS balance using RPC."""
        try:
            response = await self.rpc.getBalanceByAddress({"address": wallet_address})
            balance = float(response.get("balance", 0))
            self.logger.info(f"KAS balance for {wallet_address}: {balance}")
            return balance
        except Exception as e:
            self.logger.error(f"Error fetching KAS balance for {wallet_address}: {e}")
            return 0.0

    async def get_kasper_balance(self, wallet_address: str) -> float:
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
                self.logger.warning(f"No KASPER balance found for {wallet_address}.")
            return 0.0
        except Exception as e:
            self.logger.error(f"Error fetching KASPER balance for {wallet_address}: {e}")
            return 0.0

    async def send_kas(self, from_address: str, to_address: str, amount: float, private_key: str) -> Optional[str]:
        """Send KAS transaction."""
        try:
            response = await self.rpc.submitTransaction({
                "fromAddress": from_address,
                "toAddress": to_address,
                "amount": amount,
                "privateKey": private_key
            })
            tx_id = response.get("txId")
            self.logger.info(f"Sent {amount} KAS from {from_address} to {to_address}, TxID: {tx_id}")
            return tx_id
        except Exception as e:
            self.logger.error(f"Error sending KAS from {from_address} to {to_address}: {e}")
            return None

    async def send_krc20(self, from_address: str, to_address: str, amount: float, private_key: str) -> Optional[str]:
        """Send KRC20 (KASPER) transaction."""
        try:
            response = await self.rpc.submitTransaction({
                "fromAddress": from_address,
                "toAddress": to_address,
                "amount": amount,
                "privateKey": private_key,
                "tokenSymbol": "KASPER"
            })
            tx_id = response.get("txId")
            self.logger.info(f"Sent {amount} KASPER from {from_address} to {to_address}, TxID: {tx_id}")
            return tx_id
        except Exception as e:
            self.logger.error(f"Error sending KASPER from {from_address} to {to_address}: {e}")
            return None

    async def generate_wallet(self) -> Optional[tuple]:
        """Generate a new wallet address."""
        try:
            response = await self.rpc.createNewAddress()
            address = response.get("address")
            private_key = response.get("privateKey")
            self.logger.info(f"Generated wallet: {address}")
            return address, private_key
        except Exception as e:
            self.logger.error(f"Error generating wallet: {e}")
            return None, None
