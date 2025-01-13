// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket shim
const kaspa = require('./wasm/kaspa');
const {
    Mnemonic,
    XPrv,
    DerivationPath,
    PublicKey,
    NetworkType,
} = kaspa;

kaspa.initConsolePanicHook();

/**
 * Create a wallet with mnemonic and derive keys and addresses.
 * @param {string | null} mnemonicPhrase - Optional mnemonic phrase for wallet restoration.
 * @returns {Object} Wallet information including mnemonic, keys, and addresses.
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

        return {
            mnemonic: mnemonic.toString(),
            walletAddress: walletAddress,
            xPrv: xPrv.intoString("ktrv"),
            firstChangeAddress: firstChangeAddress,
            secondReceiveAddress: secondReceivePubKey.toAddress(NetworkType.Mainnet),
            privateKey: firstReceivePrivKey.toString(),
        };
    } catch (error) {
        console.error("Error creating wallet:", error);
        return null;
    }
};

// If this file is executed directly, create and log a new wallet
if (require.main === module) {
    (async () => {
        const wallet = await createWallet();
        if (wallet) {
            console.log("Wallet created successfully:", JSON.stringify(wallet, null, 2));
        } else {
            console.error("Failed to create wallet.");
        }
    })();
}

module.exports = { createWallet };
