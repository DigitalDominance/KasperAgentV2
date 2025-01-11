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
        const client = new MongoClient(mongoUri);
        await client.connect();
        db = client.db("kasperdb");
    } catch (err) {
        process.exit(1);
    }
}

// Retrieve user's private key from the database
async function getUserPrivateKey(user_id) {
    try {
        const user = await db.collection("users").findOne({ user_id: parseInt(user_id) }); // Ensure field name matches database
        if (!user || !user.private_key) {
            throw new Error(`Private key not found for user_id: ${user_id}`);
        }
        return user.private_key;
    } catch (err) {
        throw new Error(`Error retrieving private key: ${err.message}`);
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

        console.log(
            JSON.stringify({
                success: true,
                mnemonic: mnemonic.phrase,
                receivingAddress: receiveAddress.toString(),
                changeAddress: changeAddress.toString(),
                xPrv: xPrv.intoString("xprv"),
            })
        );
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: err.message }));
    }
}

// Get balance for an address
async function getBalance(address) {
    try {
        await rpc.connect();
        const { balances } = await rpc.getBalancesByAddresses({ addresses: [address] });
        await rpc.disconnect();

        console.log(
            JSON.stringify({
                success: true,
                address,
                balance: balances[0]?.amount || 0,
            })
        );
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: err.message }));
    }
}

// Send a KAS transaction
async function sendTransaction(user_id, fromAddress, toAddress, amount) {
    try {
        const privateKeyStr = await getUserPrivateKey(user_id);
        const privateKey = PrivateKey.fromString(privateKeyStr);

        await rpc.connect();
        const { entries } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!entries.length) throw new Error("No UTXOs available");

        const { transactions } = await createTransactions({
            entries,
            outputs: [{ address: toAddress, amount: BigInt(amount) }],
            priorityFee: 0n,
            changeAddress: fromAddress,
        });

        for (const pending of transactions) {
            await pending.sign([privateKey]);
            const txid = await pending.submit(rpc);
            console.log(JSON.stringify({ success: true, txid }));
        }

        await rpc.disconnect();
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: err.message }));
    }
}

// Send a KRC20 token transaction
async function sendKRC20Transaction(user_id, fromAddress, toAddress, amount, tokenSymbol = "KASPER") {
    try {
        const privateKeyStr = await getUserPrivateKey(user_id);
        const privateKey = PrivateKey.fromString(privateKeyStr);

        await rpc.connect();
        const { entries } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!entries.length) throw new Error("No UTXOs available");

        const payload = `krc20|${tokenSymbol}|${BigInt(amount)}`;
        const { transactions } = await createTransactions({
            entries,
            outputs: [{ address: toAddress, amount: 0n }],
            priorityFee: 0n,
            payload,
            changeAddress: fromAddress,
        });

        for (const pending of transactions) {
            await pending.sign([privateKey]);
            const txid = await pending.submit(rpc);
            console.log(JSON.stringify({ success: true, txid }));
        }

        await rpc.disconnect();
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: err.message }));
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
                    await createWallet();
                    break;
                case "getBalance":
                    await getBalance(args[0]);
                    break;
                case "sendTransaction":
                    await sendTransaction(args[0], args[1], args[2], args[3]);
                    break;
                case "sendKRC20Transaction":
                    await sendKRC20Transaction(args[0], args[1], args[2], args[3], args[4]);
                    break;
                default:
                    console.error(JSON.stringify({ success: false, error: "Invalid command" }));
            }
        } catch (e) {
            console.error(JSON.stringify({ success: false, error: e.message }));
        }
    })();
}
