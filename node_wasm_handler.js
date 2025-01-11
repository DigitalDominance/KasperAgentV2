// Global WebSocket shim for environments without native WebSocket support
globalThis.WebSocket = require("websocket").w3cwebsocket;

const kaspa = require("./wasm/kaspa");
const {
    RpcClient,
    Resolver,
    Mnemonic,
    XPrv,
    DerivationPath,
    NetworkType,
    createTransactions,
    signTransaction,
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
        console.log("Generated Mnemonic:", mnemonic.phrase);

        const seed = mnemonic.toSeed();
        const xPrv = new XPrv(seed);

        const receivePath = "m/44'/111111'/0'/0/0";
        const receiveKey = xPrv.derivePath(receivePath).toXPub().toPublicKey();
        const receiveAddress = receiveKey.toAddress(NetworkType.Mainnet);

        const changePath = "m/44'/111111'/0'/1/0";
        const changeKey = xPrv.derivePath(changePath).toXPub().toPublicKey();
        const changeAddress = changeKey.toAddress(NetworkType.Mainnet);

        console.log("Receiving Address:", receiveAddress);
        console.log("Change Address:", changeAddress);

        return {
            success: true,
            mnemonic: mnemonic.phrase,
            receivingAddress: receiveAddress,
            changeAddress,
            xPrv: xPrv.intoString("xprv"),
        };
    } catch (err) {
        console.error("Error creating wallet:", err.message);
        return { success: false, error: err.message };
    }
}

// Get balance for an address
async function getBalance(address) {
    try {
        await rpc.connect();
        const { balances } = await rpc.getBalancesByAddresses({ addresses: [address] });
        await rpc.disconnect();

        return {
            success: true,
            address,
            balance: balances[0]?.amount / 1e8 || 0, // Convert sompi to KAS
        };
    } catch (err) {
        console.error("Error fetching balance:", err.message);
        return { success: false, error: err.message };
    }
}

// Send a transaction
async function sendTransaction(fromAddress, toAddress, amount, privateKeyStr) {
    try {
        const privateKey = kaspa.PrivateKey.fromString(privateKeyStr);
        await rpc.connect();

        const { entries } = await rpc.getUtxosByAddresses([fromAddress]);

        if (!entries.length) {
            console.error("No UTXOs found for the address");
            return { success: false, error: "No UTXOs available" };
        }

        const { transactions } = await createTransactions({
            entries,
            outputs: [{ address: toAddress, amount: kaspaToSompi(amount) }],
            priorityFee: 0n,
            changeAddress: fromAddress,
        });

        for (const pending of transactions) {
            await pending.sign([privateKey]);
            const txid = await pending.submit(rpc);
            console.log("Transaction submitted, txid:", txid);
        }

        await rpc.disconnect();
        return { success: true };
    } catch (err) {
        console.error("Error sending transaction:", err.message);
        return { success: false, error: err.message };
    }
}

// Send a KRC20 token transaction
async function sendKRC20Transaction(fromAddress, toAddress, amount, privateKeyStr, tokenSymbol) {
    try {
        const privateKey = kaspa.PrivateKey.fromString(privateKeyStr);
        await rpc.connect();

        const { entries } = await rpc.getUtxosByAddresses([fromAddress]);

        if (!entries.length) {
            console.error("No UTXOs found for the address");
            return { success: false, error: "No UTXOs available" };
        }

        const payload = `krc20|${tokenSymbol}|${kaspaToSompi(amount)}`;
        const { transactions } = await createTransactions({
            entries,
            outputs: [{ address: toAddress, amount: 0n }], // Send tokens via payload
            priorityFee: 0n,
            payload,
            changeAddress: fromAddress,
        });

        for (const pending of transactions) {
            await pending.sign([privateKey]);
            const txid = await pending.submit(rpc);
            console.log(`KRC20 Transaction submitted, txid: ${txid}`);
        }

        await rpc.disconnect();
        return { success: true };
    } catch (err) {
        console.error(`Error sending ${tokenSymbol} transaction:`, err.message);
        return { success: false, error: err.message };
    }
}

// Command-line interface
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
            console.log(JSON.stringify(result, null, 2));
        } catch (e) {
            console.error(JSON.stringify({ success: false, error: e.message }));
        }
    })();
}
