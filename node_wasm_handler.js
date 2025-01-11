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
    createTransactions,
    kaspaToSompi,
    initConsolePanicHook,
} = kaspa;

const { MongoClient } = require("mongodb");

// Enable console panic hooks for debugging
initConsolePanicHook();

// Initialize RPC client
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

// MongoDB connection setup
const mongoUri = process.env.MONGODB_URI;
let db;

async function connectToDatabase() {
    try {
        const client = new MongoClient(mongoUri);
        await client.connect();
        db = client.db("kasperdb");
        console.log("Connected to MongoDB.");
    } catch (err) {
        console.error("Error connecting to MongoDB:", err);
    }
}

// Retrieve user's private key from the database
async function getUserPrivateKey(userId) {
    try {
        const user = await db.collection("users").findOne({ user_id: parseInt(userId) }); // Ensure `user_id` is used properly
        if (!user || !user.private_key) {
            throw new Error(`Private key not found for user_id: ${userId}`);
        }
        return user.private_key;
    } catch (err) {
        console.error(`Error retrieving private key for user_id ${userId}:`, err);
        throw err;
    }
}

// Utility to create a new wallet
async function createWallet() {
    try {
        const mnemonic = Mnemonic.random();
        const seed = mnemonic.toSeed();
        const xPrv = new XPrv(seed);

        const receivePath = "m/44'/111111'/0'/0/0";
        const receiveKey = xPrv.derivePath(receivePath).toXPub().toPublicKey();
        const receiveAddress = receiveKey.toAddress(NetworkType.Mainnet);

        const changePath = "m/44'/111111'/0'/1/0";
        const changeKey = xPrv.derivePath(changePath).toXPub().toPublicKey();
        const changeAddress = changeKey.toAddress(NetworkType.Mainnet);

        return {
            success: true,
            mnemonic: mnemonic.phrase,
            receivingAddress: receiveAddress.toString(),
            changeAddress: changeAddress.toString(),
            xPrv: xPrv.intoString("xprv"),
        };
    } catch (err) {
        console.error("Error creating wallet:", err);
        return { success: false, error: err.message };
    }
}

// Get balance for an address
async function getBalance(address) {
    try {
        console.log(`Fetching balance for address: ${address}`);
        await rpc.connect();

        const { balances } = await rpc.getBalancesByAddresses({ addresses: [address] });
        await rpc.disconnect();

        return {
            success: true,
            address,
            balance: balances[0]?.amount || 0, // Balance in sompi
        };
    } catch (err) {
        console.error("Error fetching balance:", err);
        return { success: false, error: err.message };
    }
}

// Send a KAS transaction
async function sendTransaction(userId, fromAddress, toAddress, amount) {
    try {
        const privateKeyStr = await getUserPrivateKey(userId);
        const privateKey = PrivateKey.fromString(privateKeyStr);

        await rpc.connect();

        const { isSynced } = await rpc.getServerInfo();
        if (!isSynced) {
            throw new Error("Node is not synced. Please wait.");
        }

        const { entries } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!entries.length) {
            throw new Error("No UTXOs available.");
        }

        entries.sort((a, b) => a.amount > b.amount ? 1 : -1); // Sort UTXOs by amount

        const { transactions } = await createTransactions({
            entries,
            outputs: [{ address: toAddress, amount: BigInt(amount) }],
            priorityFee: 0n,
            changeAddress: fromAddress,
        });

        for (const pending of transactions) {
            await pending.sign([privateKey]);
            const txid = await pending.submit(rpc);
            console.log("Transaction submitted. TXID:", txid);
        }

        await rpc.disconnect();
        return { success: true };
    } catch (err) {
        console.error("Error sending transaction:", err);
        return { success: false, error: err.message };
    }
}

// Send a KRC20 token transaction
async function sendKRC20Transaction(userId, fromAddress, toAddress, amount, tokenSymbol = "KASPER") {
    try {
        const privateKeyStr = await getUserPrivateKey(userId);
        const privateKey = PrivateKey.fromString(privateKeyStr);

        await rpc.connect();

        const { isSynced } = await rpc.getServerInfo();
        if (!isSynced) {
            throw new Error("Node is not synced. Please wait.");
        }

        const { entries } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!entries.length) {
            throw new Error("No UTXOs available.");
        }

        entries.sort((a, b) => a.amount > b.amount ? 1 : -1);

        const payload = `krc20|${tokenSymbol}|${BigInt(amount)}`; // KRC20 transfer payload
        const { transactions } = await createTransactions({
            entries,
            outputs: [{ address: toAddress, amount: 0n }], // KRC20 transfers do not require KAS outputs
            priorityFee: 0n,
            payload,
            changeAddress: fromAddress,
        });

        for (const pending of transactions) {
            await pending.sign([privateKey]);
            const txid = await pending.submit(rpc);
            console.log(`KRC20 Transaction submitted. TXID: ${txid}`);
        }

        await rpc.disconnect();
        return { success: true };
    } catch (err) {
        console.error(`Error sending ${tokenSymbol} transaction:`, err);
        return { success: false, error: err.message };
    }
}

// Command-line interface
if (require.main === module) {
    const [command, ...args] = process.argv.slice(2);

    (async () => {
        try {
            await connectToDatabase();

            let result;
            switch (command) {
                case "createWallet":
                    result = await createWallet();
                    break;
                case "getBalance":
                    result = await getBalance(args[0]);
                    break;
                case "sendTransaction":
                    result = await sendTransaction(args[0], args[1], args[2], args[3]);
                    break;
                case "sendKRC20Transaction":
                    result = await sendKRC20Transaction(args[0], args[1], args[2], args[3], args[4]);
                    break;
                default:
                    result = { success: false, error: "Invalid command" };
            }
            console.log(JSON.stringify(result, null, 2));
        } catch (e) {
            console.error("Unexpected error:", e);
        }
    })();
}
