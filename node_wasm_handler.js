const { RpcClient, Resolver, initConsolePanicHook } = require('./wasm/kaspa');

// Global WebSocket shim for environments without native WebSocket support
globalThis.WebSocket = require('websocket').w3cwebsocket;

// Enable console panic hooks for debugging
initConsolePanicHook();

// Initialize RPC client with the integrated public URLs
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet", // Specify the network (e.g., "mainnet")
});

// Create a new wallet
async function createWallet() {
    try {
        await rpc.connect();
        const wallet = await rpc.wallet.create();
        await rpc.disconnect();
        return { success: true, address: wallet.address, privateKey: wallet.privateKey };
    } catch (err) {
        console.error("Error creating wallet:", err.message);
        return { success: false, error: err.message };
    }
}

// Get the balance of an address
async function getBalance(address) {
    try {
        await rpc.connect();
        const balance = await rpc.getBalanceByAddress({ address });
        await rpc.disconnect();
        return { success: true, balance: balance.balance / 1e8 }; // Convert sompi to KAS
    } catch (err) {
        console.error("Error fetching balance:", err.message);
        return { success: false, error: err.message };
    }
}

// Send a transaction
async function sendTransaction(fromAddress, toAddress, amount, privateKey) {
    try {
        await rpc.connect();
        const tx = await rpc.submitTransaction({
            fromAddress,
            toAddress,
            amount: parseInt(amount * 1e8, 10), // Convert KAS to sompi
            privateKey,
        });
        await rpc.disconnect();
        return { success: true, transactionId: tx.transactionId };
    } catch (err) {
        console.error("Error sending transaction:", err.message);
        return { success: false, error: err.message };
    }
}

// Send a KRC20 token transaction
async function sendKRC20Transaction(fromAddress, toAddress, amount, privateKey, tokenSymbol = "KASPER") {
    try {
        await rpc.connect();
        const tx = await rpc.submitTransaction({
            fromAddress,
            toAddress,
            amount: parseInt(amount * 1e8, 10), // Convert tokens to base units
            privateKey,
            tokenSymbol,
        });
        await rpc.disconnect();
        return { success: true, transactionId: tx.transactionId };
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
                result = await sendTransaction(args[0], args[1], args[2], args[3]);
            } else if (command === "sendKRC20Transaction") {
                result = await sendKRC20Transaction(args[0], args[1], args[2], args[3], args[4]);
            } else {
                result = { success: false, error: "Invalid command" };
            }
            console.log(JSON.stringify(result));
        } catch (e) {
            console.error(JSON.stringify({ success: false, error: e.message }));
        }
    })();
}
