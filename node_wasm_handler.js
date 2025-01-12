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
    UtxoProcessor,
    UtxoContext,
    Generator,
    ScriptBuilder,
    addressFromScriptPublicKey,
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
        console.log("✅ MongoDB connection established");
    } catch (err) {
        console.error(
            JSON.stringify({ success: false, error: `Failed to connect to MongoDB: ${err.message}` })
        );
        process.exit(1);
    }
    return db;
}

// Retrieve user's private key from the database
async function getUserPrivateKey(user_id) {
    try {
        const db = await connectToDatabase();
        const user = await db.collection("users").findOne({ user_id });
        if (!user || !user.private_key) {
            throw new Error(`Private key not found for user_id: ${user_id}`);
        }
        return user.private_key;
    } catch (err) {
        throw new Error(`Error retrieving private key for user_id ${user_id}: ${err.message}`);
    }
}

// Create a new wallet
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

// Check balance of an address
async function checkBalance(address) {
    try {
        await rpc.connect();
        const { balances } = await rpc.getBalancesByAddresses({ addresses: [address] });
        const balance = balances[0]?.amount || 0n;
        console.log(
            JSON.stringify({
                success: true,
                address,
                balance: balance.toString(),
            })
        );
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: err.message }));
    } finally {
        await rpc.disconnect();
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

        const generator = new Generator({
            entries: utxos,
            outputs: [{ address: toAddress, amount: BigInt(amount) }],
            priorityFee: 1000n,
            changeAddress: fromAddress,
        });

        let pending;
        while ((pending = await generator.next())) {
            await pending.sign([privateKey]);
            const txid = await pending.submit(rpc);
            console.log(JSON.stringify({ success: true, txid }));
        }
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: err.message }));
    } finally {
        await rpc.disconnect();
    }
}

// Create the KRC20 script
function createKRC20Script(fromAddress, toAddress, amount, tokenSymbol) {
    const scriptBuilder = new ScriptBuilder();
    scriptBuilder.addData(`krc20|transfer|${tokenSymbol}|${amount}|${toAddress}`);
    const script = scriptBuilder.createPayToScriptHashScript();
    const scriptAddress = addressFromScriptPublicKey(script, "mainnet");
    return { script, scriptAddress };
}

// Send a KRC20 token transaction
async function sendKRC20Transaction(user_id, fromAddress, toAddress, amount, tokenSymbol = "KASPER") {
    try {
        const privateKeyStr = await getUserPrivateKey(user_id);
        const privateKey = new PrivateKey(privateKeyStr);

        const processor = new UtxoProcessor({ rpc, networkId: "mainnet" });
        await processor.start();
        const context = new UtxoContext({ processor });

        await rpc.connect();
        const { isSynced } = await rpc.getServerInfo();
        if (!isSynced) throw new Error("Node is not synchronized. Please try again later.");
        await context.trackAddresses([fromAddress]);

        const { script, scriptAddress } = createKRC20Script(fromAddress, toAddress, amount, tokenSymbol);

        const generator = new Generator({
            entries: context,
            outputs: [{ address: scriptAddress, amount: 0n }],
            priorityFee: 1000n,
            changeAddress: fromAddress,
        });

        let commitTxId;
        while ((pending = await generator.next())) {
            await pending.sign([privateKey]);
            commitTxId = await pending.submit(rpc);
        }

        console.log(JSON.stringify({ success: true, commitTxId }));
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: err.message }));
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
                    await createWallet();
                    break;
                case "checkBalance":
                    if (!args[0]) throw new Error("Address is required for checkBalance");
                    await checkBalance(args[0]);
                    break;
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
            console.error(JSON.stringify({ success: false, error: e.message }));
        }
    })();
}
