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

// Argument Parsing Logic
const fs = require('fs');
const path = require('path');
const nodeUtil = require('node:util');
const { parseArgs: nodeParseArgs } = nodeUtil;

/**
 * Helper function to parse command line arguments.
 * @returns {{address: string, networkId: string, encoding: Encoding}}
 */
function parseArgs() {
    const script = path.basename(process.argv[1]);
    const args = process.argv.slice(2);
    const { values } = nodeParseArgs({
        args,
        options: {
            network: { type: 'string', default: 'mainnet' },
            encoding: { type: 'string', default: 'borsh' },
            help: { type: 'boolean' },
        },
    });

    if (values.help) {
        console.log(`Usage: node ${script} [--network <mainnet|testnet-10|testnet-11>] [--encoding <borsh|json>]`);
        process.exit(0);
    }

    return {
        networkId: values.network || 'mainnet',
        encoding: values.encoding === 'json' ? Encoding.SerdeJson : Encoding.Borsh,
    };
}

const { networkId, encoding } = parseArgs();

(async () => {
    try {
        // Initialize RPC Client
        const rpc = new RpcClient({
            resolver: new Resolver(),
            networkId,
            encoding,
        });

        // Connect to Kaspa RPC
        console.log("Connecting to RPC...");
        await rpc.connect();
        console.log("Connected to RPC:", rpc.url);

        // Create Wallet Logic
        const mnemonic = Mnemonic.random();
        console.log("Generated mnemonic:", mnemonic.toString());

        const seed = mnemonic.toSeed();
        const xPrv = new XPrv(seed);

        const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
        const mainReceiveAddress = receiveWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);
        const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
        const changeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);
        const privateKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();

        // Print Wallet Details
        const walletDetails = {
            mnemonic: mnemonic.toString(),
            mainReceiveAddress: mainReceiveAddress.toString(),
            changeAddress: changeAddress.toString(),
            privateKey: privateKey.toString(),
        };

        console.log("Wallet Details:", JSON.stringify(walletDetails, null, 2));

        // Disconnect RPC
        await rpc.disconnect();
        console.log("Disconnected from RPC.");
    } catch (error) {
        console.error("Error:", error.message);
        process.exit(1);
    }
})();
