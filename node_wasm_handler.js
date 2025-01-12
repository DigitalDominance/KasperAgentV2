// Global WebSocket shim for environments without native WebSocket support
globalThis.WebSocket = require("websocket").w3cwebsocket;

const kaspa = require("./wasm/kaspa");
const {
    RpcClient,
    Resolver,
    Mnemonic,
    XPrv,
    PrivateKey,
    NetworkType,
    createTransaction,
    signTransaction,
} = kaspa;

// MongoDB connection setup
const { MongoClient } = require("mongodb");
const mongoUri = process.env.MONGODB_URI;
let db;

// Initialize RPC client
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

// Connect to MongoDB
async function connectToDatabase() {
    try {
        const client = new MongoClient(mongoUri, { useUnifiedTopology: true });
        await client.connect();
        db = client.db("kasperdb");
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: `Failed to connect to MongoDB: ${err.message}` }));
        process.exit(1);
    }
}

// Retrieve user's private key from the database
async function getUserPrivateKey(user_id) {
    try {
        if (typeof user_id !== "number") {
            throw new Error("user_id must be an integer.");
        }

        const user = await db.collection("users").findOne({ user_id });
        if (!user) {
            throw new Error(`No user found with user_id: ${user_id}`);
        }

        if (!user.private_key || typeof user.private_key !== "string") {
            throw new Error(`Private key is missing or invalid for user_id: ${user_id}`);
        }

        return user.private_key;
    } catch (err) {
        throw new Error(`Error retrieving private key for user_id ${user_id}: ${err.message}`);
    }
}

// Send a KAS transaction
async function sendTransaction(user_id, fromAddress, toAddress, amount) {
    try {
        const privateKeyStr = await getUserPrivateKey(user_id);
        const privateKey = new PrivateKey(privateKeyStr);

        await rpc.connect();
        const { entries: utxos } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!utxos.length) throw new Error("No UTXOs available");

        const outputs = [{ address: toAddress, amount: BigInt(amount) }];
        const transaction = createTransaction(utxos, outputs, 0n, "", 1);
        signTransaction(transaction, [privateKey]);

        const result = await rpc.submitTransaction({ transaction });
        console.log(JSON.stringify({ success: true, txid: result.transactionId }));
    } catch (err) {
        console.log(JSON.stringify({ success: false, error: err.message }));
    } finally {
        await rpc.disconnect();
    }
}

// Send a KRC20 token transaction
// Send a KRC20 token transaction
async function sendKRC20Transaction(user_id, fromAddress, toAddress, amount, tokenSymbol = "KASPER") {
    try {
        const privateKeyStr = await getUserPrivateKey(user_id);
        const privateKey = new PrivateKey(privateKeyStr);

        await rpc.connect();
        const { entries: utxos } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!utxos.length) {
            throw new Error("No UTXOs available");
        }

        const payload = `krc20|${tokenSymbol}|${BigInt(amount)}`;
        const outputs = [{ address: toAddress, amount: 0n }];
        const transaction = createTransaction(utxos, outputs, 0n, payload, 1);

        signTransaction(transaction, [privateKey]);
        const result = await rpc.submitTransaction({ transaction });

        console.log(JSON.stringify({ success: true, txid: result.transactionId }));
    } catch (err) {
        console.log(JSON.stringify({ success: false, error: err.message }));
    } finally {
        await rpc.disconnect();
    }
}


// Command-line interface
if (require.main === module) {
    const [command, ...args] = process.argv.slice(2);

    (async () => {
        try {
            await connectToDatabase();

            switch (command) {
                case "sendTransaction":
                    if (args.length < 4) throw new Error("Invalid arguments for sendTransaction");
                    await sendTransaction(parseInt(args[0]), args[1], args[2], args[3]);
                    break;
                case "sendKRC20Transaction":
                    if (args.length < 5) throw new Error("Invalid arguments for sendKRC20Transaction");
                    await sendKRC20Transaction(parseInt(args[0]), args[1], args[2], args[3], args[4]);
                    break;
                default:
                    console.log(JSON.stringify({ success: false, error: "Invalid command" }));
            }
        } catch (e) {
            console.log(JSON.stringify({ success: false, error: e.message }));
        }
    })();
}
