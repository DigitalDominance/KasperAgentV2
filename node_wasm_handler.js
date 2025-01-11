const {
    RpcClient,
    Resolver,
    initConsolePanicHook,
    PrivateKey,
    createTransaction,
    signTransaction,
    kaspaToSompi,
} = require('./wasm/kaspa');

// Global WebSocket shim for environments without native WebSocket support
globalThis.WebSocket = require('websocket').w3cwebsocket;

// Enable console panic hooks for debugging
initConsolePanicHook();

// Initialize RPC client with integrated resolver for public nodes
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet", // Specify the network ("mainnet" or "testnet-<number>")
});

// Create a new wallet
async function createWallet() {
    try {
        const privateKey = new PrivateKey();
        const address = privateKey.toKeypair().toAddress("mainnet");
        return {
            success: true,
            address,
            privateKey: privateKey.toString(),
        };
    } catch (err) {
        console.error("Error creating wallet:", err.message);
        return { success: false, error: err.message };
    }
}

// Get the balance of an address
async function getBalance(address) {
    try {
        await rpc.connect();
        const response = await rpc.getBalancesByAddresses({ addresses: [address] });
        const balance = response.balances[0]?.balance || 0n;
        await rpc.disconnect();
        return { success: true, balance: balance / 1e8 }; // Convert sompi to KAS
    } catch (err) {
        console.error("Error fetching balance:", err.message);
        return { success: false, error: err.message };
    }
}

// Send a KAS transaction
async function sendTransaction(fromPrivateKeyString, toAddress, amountInKAS) {
    try {
        const privateKey = PrivateKey.fromString(fromPrivateKeyString);
        const fromAddress = privateKey.toKeypair().toAddress("mainnet");

        await rpc.connect();
        const { entries: utxos } = await rpc.getUtxosByAddresses([fromAddress]);

        if (utxos.length === 0) {
            throw new Error("No UTXOs available for the source address.");
        }

        const totalAmount = kaspaToSompi(amountInKAS);

        // Prepare transaction outputs
        const outputs = [
            { address: toAddress, amount: totalAmount },
        ];

        const changeAddress = fromAddress;
        const transaction = createTransaction(utxos, outputs, 0n, "", 1);

        // Sign the transaction
        const signedTransaction = signTransaction(transaction, [privateKey], true);

        // Submit the signed transaction
        const result = await rpc.submitTransaction({ transaction: signedTransaction });
        await rpc.disconnect();

        return { success: true, transactionId: result.transactionId };
    } catch (err) {
        console.error("Error sending transaction:", err.message);
        return { success: false, error: err.message };
    }
}

// Send a KRC20 token transaction
async function sendKRC20Transaction(fromPrivateKeyString, toAddress, amountInTokens, tokenSymbol = "KASPER") {
    try {
        const privateKey = PrivateKey.fromString(fromPrivateKeyString);
        const fromAddress = privateKey.toKeypair().toAddress("mainnet");

        await rpc.connect();
        const { entries: utxos } = await rpc.getUtxosByAddresses([fromAddress]);

        if (utxos.length === 0) {
            throw new Error("No UTXOs available for the source address.");
        }

        const totalAmount = kaspaToSompi(amountInTokens);

        // Prepare KRC20 transaction outputs
        const outputs = [
            { address: toAddress, amount: totalAmount, tokenSymbol },
        ];

        const changeAddress = fromAddress;
        const transaction = createTransaction(utxos, outputs, 0n, "", 1);

        // Sign the transaction
        const signedTransaction = signTransaction(transaction, [privateKey], true);

        // Submit the signed transaction
        const result = await rpc.submitTransaction({ transaction: signedTransaction });
        await rpc.disconnect();

        return { success: true, transactionId: result.transactionId };
    } catch (err) {
        console.error(`Error sending ${tokenSymbol} transaction:`, err.message);
        return { success: false, error: err.message };
    }
}

// Command-line interface for Python
if (require.main === module) {
    const [command, ...args] = process.argv.slice(2);

    (async () => {
        try {
            let result;
            if (command === "createWallet") {
                result = await createWallet();
            } else if (command === "getBalance") {
                result = await getBalance(args[0]);
            } else if (command === "sendTransaction") {
                result = await sendTransaction(args[0], args[1], parseFloat(args[2]));
            } else if (command === "sendKRC20Transaction") {
                result = await sendKRC20Transaction(args[0], args[1], parseFloat(args[2]), args[3]);
            } else {
                result = { success: false, error: "Invalid command" };
            }
            console.log(JSON.stringify(result, null, 2));
        } catch (e) {
            console.error(JSON.stringify({ success: false, error: e.message }));
        }
    })();
}
