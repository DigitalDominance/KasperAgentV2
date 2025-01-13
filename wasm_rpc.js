const kaspa = require('./wasm/kaspa');
const {
    Mnemonic,
    XPrv,
    DerivationPath,
    PublicKey,
    NetworkType,
    Resolver,
    RpcClient,
} = kaspa;

// Initialize Kaspa RPC
const initKaspa = async () => {
    kaspa.initConsolePanicHook();
    const resolver = new Resolver();
    const rpc = new RpcClient({ resolver, networkId: 'mainnet' });

    await rpc.connect();
    console.log("Connected to Kaspa Mainnet RPC:", rpc.url);
    return rpc;
};

// Create Wallet Function
const createWallet = (mnemonicPhrase = null) => {
    try {
        // Generate or use provided mnemonic
        const mnemonic = mnemonicPhrase
            ? new Mnemonic(mnemonicPhrase)
            : Mnemonic.random();
        console.log("Mnemonic:", mnemonic.toString());

        // Generate seed from mnemonic
        const seed = mnemonic.toSeed();
        console.log("Seed:", seed);

        // Generate XPrv (extended private key)
        const xPrv = new XPrv(seed);

        // Derive the first receiving wallet (m/44'/111111'/0'/0/0)
        const walletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
        const receiveWallet = walletXPub.deriveChild(0, false).toPublicKey();
        const walletAddress = receiveWallet.toAddress(NetworkType.Mainnet);

        // Generate XPub and public key
        const xPub = xPrv.toXPub();
        const publicKey = xPub.toPublicKey();

        // Derive a change wallet (m/44'/111111'/0'/1/0)
        const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
        const changeWallet = changeWalletXPub.deriveChild(0, false).toPublicKey();
        const changeAddress = changeWallet.toAddress(NetworkType.Mainnet);

        // Output all relevant wallet details
        return {
            mnemonic: mnemonic.toString(),
            seed: seed.toString('hex'),
            xPrv: xPrv.intoString("ktrv"),
            xPub: xPub.intoString("xpub"),
            publicKey: publicKey.toString(),
            walletAddress: walletAddress,
            changeAddress: changeAddress,
        };
    } catch (error) {
        console.error("Error creating wallet:", error.message);
        return null;
    }
};

module.exports = { initKaspa, createWallet };
