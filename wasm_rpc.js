// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket shim

const kaspa = require('./wasm/kaspa');
const {
    Mnemonic,
    XPrv,
    DerivationPath,
    NetworkType,
    Resolver,
    RpcClient,
    Encoding,
} = kaspa;

kaspa.initConsolePanicHook();

(async () => {
    try {
        // Set network to Mainnet
        const networkId = NetworkType.Mainnet;

        // Initialize resolver with optional custom URLs or default public URLs
        const resolver = new Resolver({
            urls: ["https://my-kaspa-node.com", "https://backup-node.com"], // Custom URLs
        });

        // Initialize RPC client with Encoding.Borsh and updated resolver
        const rpc = new RpcClient({
            resolver,
            networkId,
            encoding: Encoding.Borsh,
        });

        // Connect to RPC endpoint
        await rpc.connect();
        console.log("Connected to RPC:", rpc.url);

        // Create a new wallet
        const mnemonic = Mnemonic.random(); // Generate a new mnemonic
        console.log("Generated mnemonic:", mnemonic.toString());

        const seed = mnemonic.toSeed();
        const xPrv = new XPrv(seed);

        // Derive wallet addresses and keys
        const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
        const receiveAddress = receiveWalletXPub.deriveChild(0, false).toPublicKey().toAddress(networkId);
        console.log("Main Receive Address:", receiveAddress.toString());

        const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
        const changeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(networkId);
        console.log("Change Address:", changeAddress.toString());

        const privateKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();
        console.log("Private Key for Main Receive Address:", privateKey.toString());

        // Print wallet information
        const walletData = {
            mnemonic: mnemonic.toString(),
            mainReceiveAddress: receiveAddress.toString(),
            changeAddress: changeAddress.toString(),
            privateKey: privateKey.toString(),
        };

        console.log("Wallet Data:", JSON.stringify(walletData, null, 2));

        // Disconnect from RPC
        await rpc.disconnect();
        console.log("Disconnected from RPC:", rpc.url);
    } catch (error) {
        console.error("Error:", error.message);
        process.exit(1);
    }
})();
