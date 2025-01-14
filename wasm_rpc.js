// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket shim
const kaspa = require('./wasm/kaspa');
const { Mnemonic, XPrv, DerivationPath, NetworkType } = kaspa;

kaspa.initConsolePanicHook();

/**
 * Create a wallet with mnemonic and derive keys and addresses.
 * @param {string | null} mnemonicPhrase - Optional mnemonic phrase for wallet restoration.
 * @returns {Object | null} Wallet information including mnemonic, keys, and addresses.
 */
const createWallet = async (mnemonicPhrase = null) => {
    try {
        // Generate or use the provided mnemonic
        const mnemonic = mnemonicPhrase ? new Mnemonic(mnemonicPhrase) : Mnemonic.random();
        console.log("Generated mnemonic:", mnemonic.toString());

        // Derive seed and master private key
        const seed = mnemonic.toSeed();
        const xPrv = new XPrv(seed);

        // Derive main receive address (m/44'/111111'/0'/0/0)
        const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
        const receiveAddressPubKey = receiveWalletXPub.deriveChild(0, false).toPublicKey();
        const walletAddress = receiveAddressPubKey.toAddress(NetworkType.Mainnet);

        // Additional derivations for debugging or extended use
        const secondReceivePubKey = receiveWalletXPub.deriveChild(1, false).toPublicKey();
        const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
        const firstChangeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

        // Derive private key for the first receive address
        const firstReceivePrivKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();

        // Construct and return wallet data
        const walletData = {
            mnemonic: mnemonic.toString(),
            walletAddress: walletAddress.toString(),
            xPrv: xPrv.intoString("ktrv"),
            firstChangeAddress: firstChangeAddress.toString(),
            secondReceiveAddress: secondReceivePubKey.toAddress(NetworkType.Mainnet).toString(),
            privateKey: firstReceivePrivKey.toString(),
        };

        console.log("Wallet data successfully generated:", JSON.stringify(walletData, null, 2));
        return walletData;
    } catch (error) {
        console.error("Error creating wallet:", error);
        return null;
    }
};

/**
 * Restore a wallet from an existing mnemonic phrase.
 * @param {string} mnemonicPhrase - The mnemonic phrase to restore the wallet.
 * @returns {Object | null} Wallet data derived from the mnemonic.
 */
const restoreWallet = async (mnemonicPhrase) => {
    if (!mnemonicPhrase) {
        console.error("Mnemonic phrase is required to restore a wallet.");
        return null;
    }

    try {
        console.log("Restoring wallet from mnemonic...");
        return await createWallet(mnemonicPhrase);
    } catch (error) {
        console.error("Error restoring wallet:", error);
        return null;
    }
};

/**
 * Main function for standalone execution
 */
if (require.main === module) {
    (async () => {
        const action = process.argv[2];
        const mnemonic = process.argv[3]; // Optional mnemonic for restore

        if (action === "create") {
            console.log("Creating a new wallet...");
            const wallet = await createWallet();
            if (wallet) {
                console.log("Wallet created successfully:");
                console.log(JSON.stringify(wallet, null, 2));
            } else {
                console.error("Failed to create wallet.");
            }
        } else if (action === "restore" && mnemonic) {
            console.log("Restoring wallet...");
            const wallet = await restoreWallet(mnemonic);
            if (wallet) {
                console.log("Wallet restored successfully:");
                console.log(JSON.stringify(wallet, null, 2));
            } else {
                console.error("Failed to restore wallet.");
            }
        } else {
            console.log("Usage:");
            console.log("  node wasm_rpc.js create             # Create a new wallet");
            console.log("  node wasm_rpc.js restore <mnemonic> # Restore a wallet using a mnemonic");
        }
    })();
}

// Export functions for external use
module.exports = { createWallet, restoreWallet };
