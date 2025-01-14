// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket module shim

const kaspa = require('./wasm/kaspa');
const {
    Mnemonic,
    XPrv,
    NetworkType,
    Resolver,
    RpcClient,
    Encoding,
} = kaspa;

kaspa.initConsolePanicHook();

/**
 * Parse command-line arguments and set defaults.
 * @returns {Object} Parsed arguments including network and encoding.
 */
function parseArgs() {
    const args = process.argv.slice(2);
    const action = args[0];
    const mnemonic = args[1] || null;

    const encoding = Encoding.Borsh; // Default encoding
    const networkId = NetworkType.Mainnet; // Default network

    if (!['create', 'restore'].includes(action)) {
        console.log(`Usage:
  node wasm_rpc.js create             # Create a new wallet
  node wasm_rpc.js restore <mnemonic> # Restore a wallet using a mnemonic`);
        process.exit(1);
    }

    return { action, mnemonic, encoding, networkId };
}

/**
 * Generate or restore a wallet.
 * @param {string | null} mnemonicPhrase Optional mnemonic for restoration.
 * @param {NetworkType} networkId Network type for address derivation.
 * @returns Wallet data.
 */
function generateWallet(mnemonicPhrase, networkId) {
    // Generate or use provided mnemonic
    const mnemonic = mnemonicPhrase ? new Mnemonic(mnemonicPhrase) : Mnemonic.random();
    console.log('Generated mnemonic:', mnemonic.toString());

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
}

(async () => {
    const { action, mnemonic, encoding, networkId } = parseArgs();

    try {
        // Initialize resolver and RPC client
        const resolver = new Resolver();
        const rpc = new RpcClient({
            resolver,
            networkId,
            encoding,
        });

        await rpc.connect();
        console.log('Connected to RPC:', rpc.url);

        if (action === 'create') {
            console.log('Creating a new wallet...');
            const wallet = generateWallet(null, networkId);
            console.log('Wallet data:', JSON.stringify(wallet, null, 2));
        } else if (action === 'restore') {
            console.log('Restoring wallet...');
            const wallet = generateWallet(mnemonic, networkId);
            console.log('Wallet data:', JSON.stringify(wallet, null, 2));
        }

        await rpc.disconnect();
        console.log('Disconnected from RPC');
    } catch (error) {
        console.error('Error:', error.message);
        process.exit(1);
    }
})();
