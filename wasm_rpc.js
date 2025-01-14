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
} = kaspa;

kaspa.initConsolePanicHook();

(async () => {
    try {
        // Initialize RPC client
        const rpc = new RpcClient({
            resolver: new Resolver(),
            networkId: "mainnet",
        });

        // Connect to the Kaspa network
        await rpc.connect();
        console.log("Connected to RPC:", rpc.url);

        // Generate a new wallet
        const mnemonic = Mnemonic.random();
        console.log("Generated mnemonic:", mnemonic.toString());

        const seed = mnemonic.toSeed();
        const xPrv = new XPrv(seed);

        // Derive wallet addresses and keys
        const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
        const receiveAddress = receiveWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);
        console.log("Main Receive Address:", receiveAddress.toString());

        const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
        const changeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);
        console.log("Change Address:", changeAddress.toString());

        const privateKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();
        console.log("Private Key for Main Receive Address:", privateKey.toString());

        // Disconnect from RPC
        await rpc.disconnect();
        console.log("Disconnected from RPC:", rpc.url);

        // Print wallet details
        const walletDetails = {
            mnemonic: mnemonic.toString(),
            mainReceiveAddress: receiveAddress.toString(),
            changeAddress: changeAddress.toString(),
            privateKey: privateKey.toString(),
        };

        console.log("Wallet Details:", JSON.stringify(walletDetails, null, 2));
    } catch (error) {
        console.error("Error:", error.message);
        process.exit(1);
    }
})();
