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

// Send a KAS transaction from the main wallet
async function sendTransactionFromMainWallet(fromAddress, toAddress, amount, mainWalletPrivateKey) {
    try {
        const privateKey = new PrivateKey(mainWalletPrivateKey);

        await rpc.connect();
        const { entries: utxos } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!utxos.length) throw new Error("No UTXOs available");

        const generator = new Generator({
            entries: utxos,
            outputs: [{ address: toAddress, amount: BigInt(amount) }],
            priorityFee: 1000n,
            changeAddress: fromAddress,
        });

        let txid;
        let pending;
        while ((pending = await generator.next())) {
            await pending.sign([privateKey]);
            txid = await pending.submit(rpc);
        }

        console.log(JSON.stringify({ success: true, txid }));
    } catch (err) {
        console.error(JSON.stringify({ success: false, error: err.message }));
    } finally {
        await rpc.disconnect();
    }
}

// Send a KAS transaction from a user wallet
async function sendTransactionFromUserWallet(user_id, fromAddress, toAddress, amount) {
    try {
        const db = await connectToDatabase();
        const user = await db.collection("users").findOne({ user_id });
        if (!user || !user.private_key) {
            throw new Error(`Private key not found for user_id: ${user_id}`);
        }
        const privateKeyStr = user.private_key;

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

        let txid;
        let pending;
        while ((pending = await generator.next())) {
            await pending.sign([privateKey]);
            txid = await pending.submit(rpc);
        }

        console.log(JSON.stringify({ success: true, txid }));
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

    let txid;
    while ((pending = await generator.next())) {
        await pending.sign([privateKey]);
        txid = await pending.submit(rpc);
    }

    return { success: true, txid };
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
