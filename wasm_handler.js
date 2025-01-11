
// W3C WebSocket module shim (required for Node.js, not needed in browsers or Bun)
globalThis.WebSocket = require('websocket').w3cwebsocket;

let kaspa = require('./wasm/kaspa'); // Ensure this matches your WASM folder structure
let { RpcClient, Resolver } = kaspa;

kaspa.initConsolePanicHook();

const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

async function createWallet() {
    try {
        const wallet = await rpc.createNewAddress();
        return wallet;
    } catch (err) {
        console.error("Error creating wallet:", err.message);
    }
}

async function getBalance(address) {
    try {
        const balance = await rpc.getBalanceByAddress({ address });
        return balance;
    } catch (err) {
        console.error("Error fetching balance:", err.message);
    }
}

async function sendTransaction(fromAddress, toAddress, amount, privateKey) {
    try {
        const tx = await rpc.submitTransaction({
            fromAddress,
            toAddress,
            amount,
            privateKey,
        });
        return tx;
    } catch (err) {
        console.error("Error sending transaction:", err.message);
    }
}

async function sendKRC20Transaction(fromAddress, toAddress, amount, privateKey, tokenSymbol = "KASPER") {
    try {
        const tx = await rpc.submitTransaction({
            fromAddress,
            toAddress,
            amount,
            privateKey,
            tokenSymbol,
        });
        return tx;
    } catch (err) {
        console.error(`Error sending ${tokenSymbol} transaction:`, err.message);
    }
}

// Command-line interface for Python
if (require.main === module) {
    const [command, ...args] = process.argv.slice(2);

    (async () => {
        try {
            if (command === "createWallet") {
                console.log(await createWallet());
            } else if (command === "getBalance") {
                console.log(await getBalance(args[0]));
            } else if (command === "sendTransaction") {
                console.log(await sendTransaction(args[0], args[1], parseFloat(args[2]), args[3]));
            } else if (command === "sendKRC20Transaction") {
                console.log(await sendKRC20Transaction(args[0], args[1], parseFloat(args[2]), args[3]));
            } else {
                console.error("Invalid command");
            }
        } catch (e) {
            console.error(e.message);
        }
    })();
}
