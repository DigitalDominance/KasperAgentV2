// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket shim

const kaspa = require('./wasm/kaspa');
const {
    Resolver,
    Encoding,
    RpcClient,
    Mnemonic,
    XPrv,
    DerivationPath,
    NetworkType,
} = kaspa;

const fs = require('fs');
const path = require('path');
kaspa.initConsolePanicHook();

/**
 * Parse command-line arguments for wallet operations.
 * @returns {Object} Parsed arguments including action, mnemonic, and encoding.
 */
function parseArgs() {
    const script = path.basename(process.argv[1]);
    const args = process.argv.slice(2);

    const action = args[0]; // "create" or "restore"
    const mnemonic = args[1]; // Optional mnemonic for restoration

    const encoding = Encoding.Borsh; // Default to Borsh encoding

    if (!["create", "restore"].includes(action)) {
        console.log(`Usage:
  node ${script} create             # Create a new wallet
  node ${script} restore <mnemonic> # Restore a wallet using a mnemonic`);
        process.exit(0);
    }

    return {
        action,
        mnemonic,
        encoding,
    };
}

(async () => {
    try {
        // Set network to Mainnet
        const networkId = NetworkType.Mainnet;

        // Parse command-line arguments
        const { action, mnemonic, encoding } = parseArgs();

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
            const mnemonic = mnemonicPhrase ? new Mnemonic(mnemonicPhrase) : Mnemonic.random();
            console.log("Generated mnemonic:", mnemonic.toString());

            const seed = mnemonic.toSeed();
            const xPrv = new XPrv(seed);

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

        if (action === "create") {
            console.log("Creating a new wallet...");
            const wallet = generateWallet(null);
            console.log(JSON.stringify(wallet, null, 2));
        } else if (action === "restore" && mnemonic) {
            console.log("Restoring wallet...");
            const wallet = generateWallet(mnemonic);
            console.log(JSON.stringify(wallet, null, 2));
        }

        // Disconnect RPC client
        await rpc.disconnect();
        console.log("Disconnected from", rpc.url);
    } catch (error) {
        console.error("Error:", error.message);
        process.exit(1);
    }
})();
