// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket shim
const kaspa = require('./wasm/kaspa');
const fs = require('fs');
const path = require('path');
const nodeUtil = require('node:util');
const { parseArgs: nodeParseArgs } = nodeUtil;

const {
    Resolver,
    Encoding,
    RpcClient,
    Mnemonic,
    XPrv,
    DerivationPath,
    NetworkType,
} = kaspa;

kaspa.initConsolePanicHook();

const {
    encoding,
} = parseArgs();

(async () => {
    try {
        // Set network to Mainnet
        const networkId = NetworkType.Mainnet;

        // Initialize resolver and RPC client
        const resolver = new Resolver();
        const rpc = new RpcClient({
            resolver,
            networkId,
            encoding,
        });

        // Connect to RPC endpoint
        await rpc.connect();
        console.log("Connected to", rpc.url);

        /**
         * Generate or restore wallet data.
         * @param {string | null} mnemonicPhrase - Optional mnemonic for restoration.
         * @returns {Object} Wallet data, including mnemonic, keys, and addresses.
         */
        const generateWallet = (mnemonicPhrase = null) => {
            // Generate or use provided mnemonic
            const mnemonic = mnemonicPhrase ? new Mnemonic(mnemonicPhrase) : Mnemonic.random();
            console.log("Generated mnemonic:", mnemonic.toString());

            const seed = mnemonic.toSeed();
            const xPrv = new XPrv(seed);

            // Derive wallet details
            const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
            const receiveAddressPubKey = receiveWalletXPub.deriveChild(0, false).toPublicKey();
            const walletAddress = receiveAddressPubKey.toAddress(networkId);

            const secondReceiveAddress = receiveWalletXPub.deriveChild(1, false).toPublicKey().toAddress(networkId);

            const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
            const firstChangeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(networkId);

            const privateKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();

            return {
                mnemonic: mnemonic.toString(),
                walletAddress: walletAddress.toString(),
                firstChangeAddress: firstChangeAddress.toString(),
                secondReceiveAddress: secondReceiveAddress.toString(),
                privateKey: privateKey.toString(),
                xPrv: xPrv.intoString("ktrv"),
            };
        };

        // Parse command-line arguments
        const action = process.argv[2];
        const mnemonic = process.argv[3];

        if (action === "create") {
            console.log("Creating a new wallet...");
            const wallet = generateWallet(null);
            console.log(JSON.stringify(wallet, null, 2));
        } else if (action === "restore" && mnemonic) {
            console.log("Restoring wallet...");
            const wallet = generateWallet(mnemonic);
            console.log(JSON.stringify(wallet, null, 2));
        } else {
            console.log(`Usage:
  node wasm_rpc.js create             # Create a new wallet
  node wasm_rpc.js restore <mnemonic> # Restore a wallet using a mnemonic`);
        }

        // Disconnect RPC client
        await rpc.disconnect();
        console.log("Disconnected from", rpc.url);
    } catch (error) {
        console.error("Error:", error.message);
        process.exit(1);
    }
})();
