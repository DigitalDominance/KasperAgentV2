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
        console.log("Creating wallet...");

        // Generate the mnemonic and keys
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

        // Explicitly output the JSON result as the last line
        const result = {
            success: true,
            mnemonic: mnemonic.phrase,
            receivingAddress: {
                version: receiveAddress.version,
                prefix: receiveAddress.prefix,
                payload: receiveAddress.payload,
            },
            changeAddress: {
                version: changeAddress.version,
                prefix: changeAddress.prefix,
                payload: changeAddress.payload,
            },
            xPrv: xPrv.intoString("xprv"),
        };

        // Ensure this is the final output to stdout
        console.log(JSON.stringify(result));
        return result;
    } catch (err) {
        console.error("Error creating wallet:", err);

        // Ensure errors are returned as JSON
        const errorResult = { success: false, error: err.message };
        console.log(JSON.stringify(errorResult));
        return errorResult;
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
            balance: balances[0]?.amount / 1e8 || 0, // Convert sompi to KAS
        };
    } catch (err) {
        console.error("Error fetching balance:", err);
        return { success: false, error: err.message };
    }
}

// Send a transaction
async function sendTransaction(fromAddress, toAddress, amount, privateKeyStr) {
    try {
        console.log(`Sending transaction from ${fromAddress} to ${toAddress} with amount ${amount}`);
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
        console.error("Error sending transaction:", err);
        return { success: false, error: err.message };
    }
}

// Send a KRC20 token transaction
async function sendKRC20Transaction(fromAddress, toAddress, amount, privateKeyStr, tokenSymbol = "KASPER") {
    try {
        console.log(`Sending KRC20 token transaction: ${amount} ${tokenSymbol} from ${fromAddress} to ${toAddress}`);
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
        console.error(`Error sending ${tokenSymbol} transaction:`, err);
        return { success: false, error: err.message };
    }
}

// Generate multiple receive/change addresses using HD wallet (xPub)
async function generateAddresses(xPrvStr, accountIndex = 0, count = 10) {
    try {
        console.log("Generating addresses...");

        const xpub = await kaspa.PublicKeyGenerator.fromMasterXPrv(xPrvStr, false, BigInt(accountIndex));

        // Generate Receive Addresses
        let receiveKeys = await xpub.receivePubkeys(0, count);
        let receiveAddresses = receiveKeys.map(key => kaspa.createAddress(key, NetworkType.Mainnet).toString());
        console.log("Receive Addresses:", receiveAddresses);

        // Generate Change Addresses
        let changeKeys = await xpub.changePubkeys(0, count);
        let changeAddresses = changeKeys.map(key => kaspa.createAddress(key, NetworkType.Mainnet).toString());
        console.log("Change Addresses:", changeAddresses);

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
