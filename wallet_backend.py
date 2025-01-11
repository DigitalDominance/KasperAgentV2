class WalletBackend:
    def __init__(self, node_script_path="node_wasm_handler.js"):
        self.node_script_path = node_script_path

    def run_node_command(self, command, *args):
        try:
            result = subprocess.run(
                ["node", self.node_script_path, command, *args],
                capture_output=True,
                text=True,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if stdout:
                logger.info(f"Node.js stdout for {command}: {stdout}")
            if stderr:
                logger.error(f"Node.js stderr for {command}: {stderr}")

            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON output: {stdout}")
                return {"success": False, "error": "Invalid JSON in Node.js output"}
        except Exception as e:
            logger.error(f"Error running {command}: {e}")
            return {"success": False, "error": str(e)}

    def create_wallet(self):
        wallet_data = self.run_node_command("createWallet")
        if wallet_data.get("success"):
            return {
                "success": True,
                "mnemonic": wallet_data["mnemonic"],
                "receiving_address": wallet_data["receivingAddress"],
                "change_address": wallet_data["changeAddress"],
                "private_key": wallet_data["xPrv"],
            }
        else:
            return wallet_data

    def get_balance(self, address):
        return self.run_node_command("getBalance", address)

    def send_transaction(self, from_address, to_address, amount, private_key):
        return self.run_node_command(
            "sendTransaction", from_address, to_address, str(amount), private_key
        )

    def send_krc20_transaction(self, from_address, to_address, amount, private_key, token_symbol="KASPER"):
        return self.run_node_command(
            "sendKRC20Transaction", from_address, to_address, str(amount), private_key, token_symbol
        )
