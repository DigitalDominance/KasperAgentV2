// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket shim

const kaspa = require('./wasm/kaspa');
const {
    Mnemonic,
    XPrv,
    DerivationPath,
    PublicKey,
    NetworkType,
    Resolver,
    RpcClient,
    Encoding,
} = kaspa;

kaspa.initConsolePanicHook();

// Initialize RPC globally to maintain persistent connection
let rpc;

(async () => {
    try {
        // Establish RPC connection with resolver
        rpc = new RpcClient({
            resolver: new Resolver(),
            networkId: "mainnet",
            encoding: Encoding.Borsh,
        });

        console.log("Connecting to RPC...");
        await rpc.connect();
        console.log("Connected to RPC:", rpc.url);

        // Start listening for commands or calls to create wallets
        console.log("Ready for wallet commands. Example: 'create_wallet'");

        process.stdin.setEncoding("utf-8");
        process.stdin.on("data", (input) => {
            const command = input.trim();

            if (command === "create_wallet") {
                const walletDetails = createWallet();
                console.log("Wallet Created:", JSON.stringify(walletDetails, null, 2));
            } else if (command === "exit") {
                console.log("Shutting down...");
                process.stdin.end();
                rpc.disconnect();
                console.log("Disconnected from RPC:", rpc.url);
            } else {
                console.log("Unknown command. Use 'create_wallet' or 'exit'.");
            }
        });
    } catch (error) {
        console.error("Error:", error.message);
        process.exit(1);
    }
})();

/**
 * Generates a new wallet with the Kaspa library.
 * @returns {Object} Wallet details including addresses and private keys.
 */
function createWallet() {
    // Generate mnemonic
    const mnemonic = Mnemonic.random();
    console.log("Generated mnemonic:", mnemonic.toString());

    const seed = mnemonic.toSeed();
    const xPrv = new XPrv(seed);

    // Derive wallet addresses and private keys
    const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
    const mainReceiveAddress = receiveWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

    const secondReceiveAddress = receiveWalletXPub.deriveChild(1, false).toPublicKey().toAddress(NetworkType.Mainnet);

    const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
    const changeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

    const privateKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();

    return {
        mnemonic: mnemonic.toString(),
        mainReceiveAddress: mainReceiveAddress.toString(),
        secondReceiveAddress: secondReceiveAddress.toString(),
        changeAddress: changeAddress.toString(),
        privateKey: privateKey.toString(),
    };
}
