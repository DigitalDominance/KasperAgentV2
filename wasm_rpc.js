// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket shim
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
    Address,
    Encoding,
} = kaspa;

kaspa.initConsolePanicHook();

/**
 * Helper function to parse command line arguments for running the script.
 * @param {Object} options - Additional options for argument parsing.
 * @returns {Object} Parsed arguments including address, networkId, and encoding.
 */
function parseArgs(options = { additionalParseArgs: {}, additionalHelpOutput: '' }) {
    const script = path.basename(process.argv[1]);
    const args = process.argv.slice(2);

    const { values, positionals, tokens } = nodeParseArgs({
        args,
        options: {
            ...options.additionalParseArgs,
            help: { type: 'boolean' },
            json: { type: 'boolean' },
            address: { type: 'string' },
            network: { type: 'string' },
            encoding: { type: 'string' },
        },
        tokens: true,
        allowPositionals: true,
    });

    if (values.help) {
        console.log(`Usage: node ${script} create|restore [options]
Options:
  --address <address>         Specify wallet address.
  --network <mainnet|testnet> Specify the network type.
  --encoding <borsh|json>     Specify encoding type. ${options.additionalHelpOutput}`);
        process.exit(0);
    }

    const addressRegex = /(kaspa|kaspatest):\S+/i;
    const addressArg = values.address ?? positionals.find((positional) => addressRegex.test(positional)) ?? null;
    const address = addressArg === null ? null : new Address(addressArg);

    const networkArg = values.network ?? 'mainnet';
    const networkId = new NetworkType(networkArg);

    const encodingArg = values.encoding ?? 'borsh';
    const encoding = encodingArg === 'json' ? Encoding.SerdeJson : Encoding.Borsh;

    return { address, networkId, encoding, tokens };
}

/**
 * Derive wallet details from an XPrv key.
 * @param {XPrv} xPrv - Extended private key.
 * @param {NetworkType} networkType - Network type (Mainnet or Testnet).
 * @returns {Object} Wallet details including addresses and keys.
 */
const deriveWalletData = (xPrv, networkType) => {
    const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
    const receiveAddressPubKey = receiveWalletXPub.deriveChild(0, false).toPublicKey();
    const walletAddress = receiveAddressPubKey.toAddress(networkType);

    const secondReceiveAddress = receiveWalletXPub.deriveChild(1, false).toPublicKey().toAddress(networkType);

    const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
    const firstChangeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(networkType);

    const privateKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();

    return {
        mnemonic: xPrv.toMnemonic().toString(),
        walletAddress: walletAddress.toString(),
        firstChangeAddress: firstChangeAddress.toString(),
        secondReceiveAddress: secondReceiveAddress.toString(),
        privateKey: privateKey.toString(),
        xPrv: xPrv.intoString("ktrv"),
    };
};

/**
 * Create or restore a wallet.
 * @param {string | null} mnemonicPhrase - Optional mnemonic phrase for restoration.
 * @param {NetworkType} networkType - Network type.
 * @returns {Object} Wallet details.
 */
const createOrRestoreWallet = (mnemonicPhrase, networkType) => {
    const mnemonic = mnemonicPhrase ? new Mnemonic(mnemonicPhrase) : Mnemonic.random();
    const seed = mnemonic.toSeed();
    const xPrv = new XPrv(seed);
    return deriveWalletData(xPrv, networkType);
};

/**
 * Main function for the command-line interface.
 */
if (require.main === module) {
    const { address, networkId, encoding } = parseArgs({
        additionalHelpOutput: "Use this script to create or restore wallets on the Kaspa blockchain.",
    });

    const action = process.argv[2];
    const mnemonic = process.argv[3];

    try {
        if (action === "create") {
            console.log("Creating a new wallet...");
            const wallet = createOrRestoreWallet(null, networkId);
            console.log(JSON.stringify(wallet, null, 2));
        } else if (action === "restore" && mnemonic) {
            console.log("Restoring wallet from mnemonic...");
            const wallet = createOrRestoreWallet(mnemonic, networkId);
            console.log(JSON.stringify(wallet, null, 2));
        } else {
            console.log(`Usage:
  node wasm_rpc.js create             # Create a new wallet
  node wasm_rpc.js restore <mnemonic> # Restore a wallet using a mnemonic`);
        }
    } catch (error) {
        console.error("Error occurred:", error.message);
    }
}

// Export functions for external use
module.exports = { createOrRestoreWallet };
