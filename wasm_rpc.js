const kaspa = require('./wasm/kaspa');
const { Mnemonic, XPrv, NetworkType, Resolver, RpcClient } = kaspa;

const initKaspa = async () => {
    kaspa.initConsolePanicHook();
    const resolver = new Resolver();
    const rpc = new RpcClient({ resolver, networkId: 'mainnet' });

    await rpc.connect();
    console.log("Connected to Kaspa Mainnet RPC:", rpc.url);
    return rpc;
};

const createWallet = (mnemonicPhrase = null) => {
    const mnemonic = mnemonicPhrase ? new Mnemonic(mnemonicPhrase) : Mnemonic.random();
    const seed = mnemonic.toSeed();
    const xPrv = new XPrv(seed);
    const walletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
    const receiveWallet = walletXPub.deriveChild(0, false).toPublicKey();
    const walletAddress = receiveWallet.toAddress(NetworkType.Mainnet);

    return { mnemonic: mnemonic.toString(), address: walletAddress };
};

module.exports = { initKaspa, createWallet };
