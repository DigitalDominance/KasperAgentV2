import subprocess
import json

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
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                raise Exception(result.stderr.strip())
        except Exception as e:
            print(f"Error: {e}")
            return None

    def create_wallet(self):
        return self.run_node_command("createWallet")

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
