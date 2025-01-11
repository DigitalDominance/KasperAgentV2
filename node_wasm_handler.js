// W3C WebSocket module shim (required for Node.js, not needed in browsers or Bun)
globalThis.WebSocket = require('websocket').w3cwebsocket;

let kaspa = require('./wasm/kaspa'); // Ensure this matches your WASM folder structure
let { RpcClient, Resolver } = kaspa;

kaspa.initConsolePanicHook();

const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

// Create a new wallet
async function createWallet() {
    try {
        const wallet = await rpc.createNewAddress();
        return { success: true, address: wallet.address, privateKey: wallet.privateKey };
    } catch (err) {
        console.error("Error creating wallet:", err.message);
        return { success: false, error: err.message };
    }
}

// Get the balance of an address
async function getBalance(address) {
    try {
        const balance = await rpc.getBalanceByAddress({ address });
        return { success: true, balance: balance.balance };
    } catch (err) {
        console.error("Error fetching balance:", err.message);
        return { success: false, error: err.message };
    }
}

// Send a transaction
async function sendTransaction(fromAddress, toAddress, amount, privateKey) {
    try {
        const tx = await rpc.submitTransaction({
            fromAddress,
            toAddress,
            amount: parseFloat(amount),
            privateKey,
        });
        return { success: true, transactionId: tx.transactionId };
    } catch (err) {
        console.error("Error sending transaction:", err.message);
        return { success: false, error: err.message };
    }
}

// Send a KRC20 token transaction
async function sendKRC20Transaction(fromAddress, toAddress, amount, privateKey, tokenSymbol = "KASPER") {
    try {
        const tx = await rpc.submitTransaction({
            fromAddress,
            toAddress,
            amount: parseFloat(amount),
            privateKey,
            tokenSymbol,
        });
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
