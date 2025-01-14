// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket module shim

const kaspa = require('./wasm/kaspa');
const fs = require('fs');
const path = require('path');
const nodeUtil = require('node:util');
const { parseArgs: nodeParseArgs } = nodeUtil;

const {
    Mnemonic,
    XPrv,
    DerivationPath,
    NetworkType,
    Resolver,
    RpcClient,
    Encoding,
} = kaspa;

kaspa.initConsolePanicHook();

/**
 * Helper function to parse command-line arguments.
 * @returns Parsed arguments for the script.
 */
function parseArgs() {
    const args = process.argv.slice(2);
    const {
        values,
        positionals,
    } = nodeParseArgs({
        args,
        options: {
            help: { type: 'boolean' },
            network: { type: 'string' },
            encoding: { type: 'string' },
        },
    });

    if (values.help) {
        console.log(`Usage: node wasm_rpc.js <create|restore> [mnemonic]`);
        process.exit(0);
    }

    return {
        network: values.network || 'mainnet',
        encoding: values.encoding || Encoding.Borsh,
    };
}

/**
 * Generate or restore a wallet.
 * @param {string | null} mnemonicPhrase Optional mnemonic for restoration.
 * @returns Wallet data.
 */
function generateWallet(mnemonicPhrase = null) {
    // Generate or use provided mnemonic
    const mnemonic = mnemonicPhrase ? new Mnemonic(mnemonicPhrase) : Mnemonic.random();
    console.log('Generated mnemonic:', mnemonic.toString());

    const seed = mnemonic.toSeed();
    const xPrv = new XPrv(seed);

    // Derive wallet details
    const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
    const receiveAddressPubKey = receiveWalletXPub.deriveChild(0, false).toPublicKey();
    const walletAddress = receiveAddressPubKey.toAddress(NetworkType.Mainnet);

    const secondReceiveAddress = receiveWalletXPub.deriveChild(1, false).toPublicKey().toAddress(NetworkType.Mainnet);

    const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
    const firstChangeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

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
    const { network, encoding } = parseArgs();

    try {
        // Initialize resolver and RPC client
        const resolver = new Resolver();
        const rpc = new RpcClient({
            resolver,
            networkId: NetworkType.Mainnet, // Using Mainnet
            encoding,
        });

        await rpc.connect();
        console.log('Connected to RPC:', rpc.url);

        const action = process.argv[2];
        const mnemonic = process.argv[3];

        if (action === 'create') {
            console.log('Creating a new wallet...');
            const wallet = generateWallet(null);
            console.log('Wallet data:', JSON.stringify(wallet, null, 2));
        } else if (action === 'restore' && mnemonic) {
            console.log('Restoring wallet...');
            const wallet = generateWallet(mnemonic);
            console.log('Wallet data:', JSON.stringify(wallet, null, 2));
        } else {
            console.log(`Usage:
  node wasm_rpc.js create             # Create a new wallet
  node wasm_rpc.js restore <mnemonic> # Restore a wallet using a mnemonic`);
        }

        await rpc.disconnect();
        console.log('Disconnected from RPC');
    } catch (error) {
        console.error('Error:', error.message);
        process.exit(1);
    }
})();
