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

// Enable console panic hooks for debugging
initConsolePanicHook();

// Initialize RPC client with the integrated public URLs
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

// Utility to create wallet
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
async function sendTransaction(fromAddress, toAddress, amount, privateKeyStr) {
    try {
        const privateKey = new kaspa.PrivateKey(privateKeyStr);
        const sourceAddress = privateKey.toKeypair().toAddress("mainnet"); // Adjust networkId if necessary
        console.info(`Source address: ${sourceAddress}`);

        await rpc.connect();

        const { isSynced } = await rpc.getServerInfo();
        if (!isSynced) {
            console.error("Node is not synced. Please wait.");
            await rpc.disconnect();
            return { success: false, error: "Node is not synced" };
        }

        const { entries } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!entries.length) {
            return { success: false, error: "No UTXOs available" };
        }

        entries.sort((a, b) => a.amount > b.amount ? 1 : -1); // Sort UTXOs by amount

        const { transactions } = await createTransactions({
            entries,
            outputs: [{ address: toAddress, amount: BigInt(amount) }],
            priorityFee: 0n,
            changeAddress: fromAddress,
        });

        for (const pending of transactions) {
            console.log("Signing transaction with private key...");
            await pending.sign([privateKey]);
            console.log("Submitting transaction...");
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
async function sendKRC20Transaction(fromAddress, toAddress, amount, privateKeyStr, tokenSymbol = "KASPER") {
    try {
        const privateKey = new kaspa.PrivateKey(privateKeyStr);
        const sourceAddress = privateKey.toKeypair().toAddress("mainnet");
        console.info(`Source address: ${sourceAddress}`);

        await rpc.connect();

        const { isSynced } = await rpc.getServerInfo();
        if (!isSynced) {
            console.error("Node is not synced. Please wait.");
            await rpc.disconnect();
            return { success: false, error: "Node is not synced" };
        }

        const { entries } = await rpc.getUtxosByAddresses([fromAddress]);
        if (!entries.length) {
            return { success: false, error: "No UTXOs available" };
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
            console.log("Signing KRC20 transaction...");
            await pending.sign([privateKey]);
            console.log("Submitting KRC20 transaction...");
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

// Generate multiple receive/change addresses using HD wallet (xPub)
async function generateAddresses(xPrvStr, accountIndex = 0, count = 10) {
    try {
        const xpub = await kaspa.PublicKeyGenerator.fromMasterXPrv(xPrvStr, false, BigInt(accountIndex));

        const receiveKeys = await xpub.receivePubkeys(0, count);
        const receiveAddresses = receiveKeys.map(key => kaspa.createAddress(key, NetworkType.Mainnet).toString());

        const changeKeys = await xpub.changePubkeys(0, count);
        const changeAddresses = changeKeys.map(key => kaspa.createAddress(key, NetworkType.Mainnet).toString());

        return {
            success: true,
            receiveAddresses,
            changeAddresses,
        };
    } catch (err) {
        console.error("Error generating addresses:", err);
        return { success: false, error: err.message };
    }
}

// Command-line interface
if (require.main === module) {
    const [command, ...args] = process.argv.slice(2);

    (async () => {
        try {
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
                case "generateAddresses":
                    result = await generateAddresses(args[0], args[1] || 0, args[2] || 10);
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
