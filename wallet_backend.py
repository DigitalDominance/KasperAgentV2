import subprocess
import json


class WalletBackend:
    def __init__(self, node_script_path="node_wasm_handler.js"):
        self.node_script_path = node_script_path

    def run_node_command(self, command, *args):
        """
        Execute the Node.js script with the given command and arguments.

        Args:
            command (str): The command to execute (e.g., createWallet, getBalance).
            *args: Additional arguments for the command.

        Returns:
            dict: The parsed JSON response from the Node.js script.
        """
        try:
            result = subprocess.run(
                ["node", self.node_script_path, command, *args],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                # Parse JSON output from the Node.js script
                return json.loads(result.stdout)
            else:
                raise Exception(result.stderr.strip())
        except Exception as e:
            print(f"Error: {e}")
            return {"success": False, "error": str(e)}

    def create_wallet(self):
        """
        Create a new wallet and return its mnemonic, addresses, and xPrv key.

        Returns:
            dict: The wallet creation details or an error message.
        """
        return self.run_node_command("createWallet")

    def get_balance(self, address):
        """
        Get the balance of a given address.

        Args:
            address (str): The wallet address to check.

        Returns:
            dict: The balance information or an error message.
        """
        return self.run_node_command("getBalance", address)

    def send_transaction(self, from_address, to_address, amount, private_key):
        """
        Send KAS from one address to another.

        Args:
            from_address (str): The source wallet address.
            to_address (str): The destination wallet address.
            amount (float): Amount to send in KAS.
            private_key (str): The private key of the source address.

        Returns:
            dict: The transaction result or an error message.
        """
        return self.run_node_command(
            "sendTransaction", from_address, to_address, str(amount), private_key
        )

    def send_krc20_transaction(self, from_address, to_address, amount, private_key, token_symbol="KASPER"):
        """
        Send a KRC20 token transaction.

        Args:
            from_address (str): The source wallet address.
            to_address (str): The destination wallet address.
            amount (float): The amount of the token to send.
            private_key (str): The private key of the source address.
            token_symbol (str): The symbol of the KRC20 token (default: "KASPER").

        Returns:
            dict: The transaction result or an error message.
        """
        return self.run_node_command(
            "sendKRC20Transaction", from_address, to_address, str(amount), private_key, token_symbol
        )
