// Global WebSocket shim for environments without native WebSocket support
globalThis.WebSocket = require("websocket").w3cwebsocket;

const kaspa = require("./wasm/kaspa");
const {
    Mnemonic,
    XPrv,
    NetworkType,
    initConsolePanicHook,
    RpcClient,
    Resolver,
} = kaspa;

// Enable console panic hooks for debugging
initConsolePanicHook();

// Initialize RPC client with the integrated public URLs
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

// Utility function to create a wallet
async function createWallet() {
    try {
        console.log("Creating wallet...");

        // Generate a new mnemonic
        const mnemonic = Mnemonic.random();
        console.log("Generated Mnemonic:", mnemonic.phrase);

        // Derive keys and addresses
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

// Command-line interface for creating a wallet
if (require.main === module) {
    (async () => {
        const result = await createWallet();
        console.log(JSON.stringify(result, null, 2));
    })();
}
