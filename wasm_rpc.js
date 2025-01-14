// @ts-ignore
globalThis.WebSocket = require('websocket').w3cwebsocket; // W3C WebSocket shim

const kaspa = require('./wasm/kaspa');
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

const fs = require('fs');
const path = require('path');
const nodeUtil = require('node:util');
const { parseArgs: nodeParseArgs } = nodeUtil;

/**
 * Helper function to parse command line arguments.
 * @returns {{action: string, mnemonic?: string, encoding: Encoding}}
 */
function parseArgs() {
    const script = path.basename(process.argv[1]);
    const args = process.argv.slice(2);

    const { values, positionals } = nodeParseArgs({
        args,
        options: {
            encoding: { type: 'string', default: 'borsh' },
            help: { type: 'boolean' },
        },
        allowPositionals: true,
    });

    if (values.help || positionals.length === 0) {
        console.log(`Usage:
  node ${script} create                       # Create a new wallet
  node ${script} restore <mnemonic>          # Restore a wallet using a mnemonic
`);
        process.exit(0);
    }

    const [action, mnemonic] = positionals;

    if (action !== 'create' && action !== 'restore') {
        console.error(`Invalid action: ${action}`);
        process.exit(1);
    }

    return {
        action,
        mnemonic,
        encoding: values.encoding === 'json' ? Encoding.SerdeJson : Encoding.Borsh,
    };
}

const { action, mnemonic, encoding } = parseArgs();

(async () => {
    try {
        // Initialize RPC Client
        const rpc = new RpcClient({
            resolver: new Resolver(),
            networkId: "mainnet",
            encoding,
        });

        // Connect to RPC
        console.log("Connecting to RPC...");
        await rpc.connect();
        console.log("Connected to RPC:", rpc.url);

        // Wallet logic
        if (action === 'create') {
            const newMnemonic = Mnemonic.random();
            console.log("Generated mnemonic:", newMnemonic.toString());

            const seed = newMnemonic.toSeed();
            const xPrv = new XPrv(seed);

            const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
            const mainReceiveAddress = receiveWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

            console.log("Main Receive Address:", mainReceiveAddress.toString());
        } else if (action === 'restore') {
            if (!mnemonic) {
                console.error("Mnemonic is required to restore a wallet.");
                process.exit(1);
            }

            const restoredMnemonic = new Mnemonic(mnemonic);
            console.log("Restored mnemonic:", restoredMnemonic.toString());

            const seed = restoredMnemonic.toSeed();
            const xPrv = new XPrv(seed);

            const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
            const mainReceiveAddress = receiveWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

            console.log("Restored Main Receive Address:", mainReceiveAddress.toString());
        }

        // Disconnect from RPC
        await rpc.disconnect();
        console.log("Disconnected from RPC.");
    } catch (error) {
        console.error("Error:", error.message);
        process.exit(1);
    }
})();
