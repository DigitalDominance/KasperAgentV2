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
} = kaspa;

const { MongoClient } = require("mongodb");
const mongoUri = process.env.MONGODB_URI;
let db;

// Initialize RPC client
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

// Singleton Database Connection
async function connectToDatabase() {
    if (db) return db;

    try {
        const client = new MongoClient(mongoUri, { useUnifiedTopology: true });
        await client.connect();
        db = client.db("kasperdb");
    } catch (err) {
        throw new Error(`Failed to connect to MongoDB: ${err.message}`);
    }
    return db;
}

// Retrieve user's private key from the database
async function getUserPrivateKey(user_id) {
    const db = await connectToDatabase();
    const user = await db.collection("users").findOne({ user_id });
    if (!user || !user.private_key) {
        throw new Error(`Private key not found for user_id: ${user_id}`);
    }
    return user.private_key;
}

// Create a new wallet
async function createWallet() {
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
}

// Check balance of an address
async function checkBalance(address) {
    try {
        await rpc.connect();
        const { balances } = await rpc.getBalancesByAddresses({ addresses: [address] });
        const balance = balances[0]?.amount || 0n;
        return {
            success: true,
            address,
            balance: balance.toString(),
        };
    } catch (err) {
        return { success: false, error: err.message };
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
                case "createWallet":
                    console.log(JSON.stringify(await createWallet()));
                    break;
                case "checkBalance":
                    if (!args[0]) throw new Error("Address is required for checkBalance");
                    console.log(JSON.stringify(await checkBalance(args[0])));
                    break;
                case "sendTransaction":
                    if (args.length < 4) throw new Error("Invalid arguments for sendTransaction");
                    console.log(JSON.stringify(await sendTransaction(parseInt(args[0]), args[1], args[2], args[3])));
                    break;
                case "sendKRC20Transaction":
                    if (args.length < 5) throw new Error("Invalid arguments for sendKRC20Transaction");
                    console.log(JSON.stringify(await sendKRC20Transaction(parseInt(args[0]), args[1], args[2], args[3], args[4])));
                    break;
                default:
                    console.log(JSON.stringify({ success: false, error: "Invalid command" }));
            }
        } catch (e) {
            console.error(JSON.stringify({ success: false, error: e.message }));
        }
    })();
}
