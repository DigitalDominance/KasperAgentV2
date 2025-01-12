// Global WebSocket shim for environments without native WebSocket support
globalThis.WebSocket = require("websocket").w3cwebsocket;

const kaspa = require("./wasm/kaspa");
const { RpcClient, Resolver, Mnemonic, XPrv, NetworkType } = kaspa;

const { MongoClient } = require("mongodb");
const mongoUri = process.env.MONGODB_URI;

let db;
let rpc;

// Initialize RPC client
async function initializeRpcClient() {
    if (rpc && rpc.isConnected) return rpc;

    console.log("Initializing RPC client...");
    rpc = new RpcClient({
        resolver: new Resolver(),
        networkId: "mainnet",
    });

    try {
        await rpc.connect();
        console.log("RPC client connected successfully.");
    } catch (err) {
        console.error(`Failed to connect RPC client: ${err.message}`);
        throw new Error("Could not connect to Kaspa RPC.");
    }

    return rpc;
}

// Singleton Database Connection
let dbPromise = null;
async function connectToDatabase() {
    if (dbPromise) return dbPromise;

    dbPromise = (async () => {
        try {
            console.log("Connecting to MongoDB...");
            const client = new MongoClient(mongoUri, { useUnifiedTopology: true });
            await client.connect();
            console.log("MongoDB connected.");
            return client.db("kasperdb");
        } catch (err) {
            console.error(`Failed to connect to MongoDB: ${err.message}`);
            dbPromise = null; // Reset if connection fails
            throw err;
        }
    })();

    return dbPromise;
}

// Retrieve user's private key from the database
async function getUserPrivateKey(user_id) {
    try {
        const db = await connectToDatabase();
        console.log(`Fetching private key for user_id: ${user_id}`);

        const user = await db.collection("users").findOne({ user_id });
        if (!user || !user.private_key) {
            throw new Error(`Private key not found for user_id: ${user_id}`);
        }

        console.log("Private key retrieved successfully.");
        return { success: true, privateKey: user.private_key };
    } catch (err) {
        console.error(`Error fetching private key: ${err.message}`);
        return { success: false, error: err.message };
    }
}

// Create a new wallet
async function createWallet(retries = 3) {
    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            console.log(`Starting wallet creation (Attempt ${attempt})...`);
            const rpcClient = await initializeRpcClient();

            const mnemonic = Mnemonic.random();
            console.log("Mnemonic generated.");

            const seed = mnemonic.toSeed();
            console.log("Seed derived.");

            const xPrv = new XPrv(seed);
            console.log("Master key created.");

            const receivePath = "m/44'/111111'/0'/0/0";
            const receiveKey = xPrv.derivePath(receivePath).toXPub().toPublicKey();
            const receiveAddress = receiveKey.toAddress(NetworkType.Mainnet);
            console.log(`Receiving address derived: ${receiveAddress.toString()}`);

            const changePath = "m/44'/111111'/0'/1/0";
            const changeKey = xPrv.derivePath(changePath).toXPub().toPublicKey();
            const changeAddress = changeKey.toAddress(NetworkType.Mainnet);
            console.log(`Change address derived: ${changeAddress.toString()}`);

            return {
                success: true,
                mnemonic: mnemonic.phrase,
                receivingAddress: receiveAddress.toString(),
                changeAddress: changeAddress.toString(),
                xPrv: xPrv.intoString("xprv"),
            };
        } catch (err) {
            console.error(`Error during wallet creation (Attempt ${attempt}): ${err.message}`);
            if (attempt === retries) {
                return { success: false, error: "Max retries reached during wallet creation." };
            }
        }
    }
}

// Check balance of an address
async function checkBalance(address) {
    try {
        const rpcClient = await initializeRpcClient();
        console.log(`Checking balance for address: ${address}`);

        const { balances } = await rpcClient.getBalancesByAddresses({ addresses: [address] });
        const balance = balances[0]?.amount || 0n;

        console.log(`Balance retrieved: ${balance.toString()}`);
        return {
            success: true,
            address,
            balance: balance.toString(),
        };
    } catch (err) {
        console.error(`Error checking balance: ${err.message}`);
        return { success: false, error: err.message };
    }
}

// Command-line interface
if (require.main === module) {
    const [command, ...args] = process.argv.slice(2);

    (async () => {
        try {
            switch (command) {
                case "createWallet":
                    console.log(JSON.stringify(await createWallet()));
                    break;
                case "checkBalance":
                    if (!args[0]) throw new Error("Address is required for checkBalance");
                    console.log(JSON.stringify(await checkBalance(args[0])));
                    break;
                case "getUserPrivateKey":
                    if (!args[0]) throw new Error("User ID is required for getUserPrivateKey");
                    console.log(JSON.stringify(await getUserPrivateKey(args[0])));
                    break;
                default:
                    console.log(JSON.stringify({ success: false, error: "Invalid command" }));
            }
        } catch (e) {
            console.error(JSON.stringify({ success: false, error: e.message }));
        }
    })();
}
