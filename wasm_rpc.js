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

// Initialize RPC client
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

console.log("Connecting to RPC...");
rpc.connect()
    .then(() => {
        console.log("Connected to RPC:", rpc.url);

        // Generate wallet after successful connection
        const generateWallet = () => {
            const mnemonic = Mnemonic.random();
            console.log("Generated mnemonic:", mnemonic.toString());

            const seed = mnemonic.toSeed();
            const xPrv = new XPrv(seed);

            // Derive wallet addresses and keys
            const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
            const receiveAddress = receiveWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

            const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
            const changeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

            const privateKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();

            // Wallet details
            const walletDetails = {
                mnemonic: mnemonic.toString(),
                mainReceiveAddress: receiveAddress.toString(),
                changeAddress: changeAddress.toString(),
                privateKey: privateKey.toString(),
            };

            console.log("Wallet Details:", JSON.stringify(walletDetails, null, 2));
        };

        // Generate wallet
        generateWallet();

        // Disconnect from RPC
        return rpc.disconnect();
    })
    .then(() => {
        console.log("Disconnected from RPC");
    })
    .catch((error) => {
        console.error("Error:", error.message);
        process.exit(1);
    });
