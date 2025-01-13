const kaspa = require('./wasm/kaspa');
const {
    Mnemonic,
    XPrv,
    NetworkType,
    Resolver,
    RpcClient
} = kaspa;

const initKaspa = async () => {
    try {
        kaspa.initConsolePanicHook();
        const resolver = new Resolver();
        const rpc = new RpcClient({ resolver, networkId: 'mainnet' });

        await rpc.connect();
        console.log("Connected to Kaspa Mainnet RPC:", rpc.url);

        return rpc;
    } catch (error) {
        console.error("Error initializing Kaspa RPC:", error.message);
        throw error;
    }
};

const createWallet = async (mnemonicPhrase = null) => {
    try {
        // Initialize RPC
        const rpc = await initKaspa();

        // Use provided mnemonic or generate a new one
        const mnemonic = mnemonicPhrase
            ? new Mnemonic(mnemonicPhrase)
            : Mnemonic.random();
        console.log("Mnemonic:", mnemonic.toString());

        // Generate seed from mnemonic
        const seed = mnemonic.toSeed();
        console.log("Seed:", seed.toString('hex'));

        // Generate extended private key (xPrv)
        const xPrv = new XPrv(seed);

        // Derive receiving address (m/44'/111111'/0'/0/0)
        const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
        const receiveWallet = receiveWalletXPub.deriveChild(0, false).toPublicKey();
        const walletAddress = receiveWallet.toAddress(NetworkType.Mainnet);

        console.log("Wallet Address:", walletAddress);

        // Derive change address (m/44'/111111'/0'/1/0)
        const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
        const changeWallet = changeWalletXPub.deriveChild(0, false).toPublicKey();
        const changeAddress = changeWallet.toAddress(NetworkType.Mainnet);

        console.log("Change Address:", changeAddress);

        // Close RPC connection
        await rpc.disconnect();
        console.log("Disconnected from Kaspa Mainnet RPC.");

        // Return wallet details
        return {
            mnemonic: mnemonic.toString(),
            seed: seed.toString('hex'),
            xPrv: xPrv.intoString("ktrv"),
            xPub: xPrv.toXPub().intoString("xpub"),
            publicKey: xPrv.toXPub().toPublicKey().toString(),
            walletAddress: walletAddress,
            changeAddress: changeAddress,
        };
    } catch (error) {
        console.error("Error creating wallet:", error.message);
        throw error;
    }
};

// Example Usage
(async () => {
    try {
        const wallet = await createWallet();
        console.log("Wallet Generated Successfully:");
        console.log(JSON.stringify(wallet, null, 2));
    } catch (error) {
        console.error("Failed to create wallet:", error.message);
    }
})();

module.exports = { initKaspa, createWallet };
