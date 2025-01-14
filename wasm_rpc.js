// @ts-ignore
globalThis.WebSocket = require("websocket").w3cwebsocket; // W3C WebSocket shim

const readline = require("readline");
const kaspa = require("./wasm/kaspa");
const {
  Mnemonic,
  XPrv,
  DerivationPath,
  PublicKey,
  NetworkType,
  Resolver,
  RpcClient,
} = kaspa;

kaspa.initConsolePanicHook();

const rpc = new RpcClient({
  resolver: new Resolver(),
  networkId: "mainnet",
});

rpc.connect().then(() => {
  console.log("Connected to Kaspa RPC");
});

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false,
});

function createWallet() {
    const mnemonic = Mnemonic.random();
    const seed = mnemonic.toSeed();
    const xPrv = new XPrv(seed);

    const receiveWalletXPub = xPrv.derivePath("m/44'/111111'/0'/0").toXPub();
    const mainReceiveAddress = receiveWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

    const changeWalletXPub = xPrv.derivePath("m/44'/111111'/0'/1").toXPub();
    const changeAddress = changeWalletXPub.deriveChild(0, false).toPublicKey().toAddress(NetworkType.Mainnet);

    const privateKey = xPrv.derivePath("m/44'/111111'/0'/0/0").toPrivateKey();

    return {
        mnemonic: mnemonic.toString(),
        mainReceiveAddress: mainReceiveAddress.toString(),
        changeAddress: changeAddress.toString(),
        privateKey: privateKey.toString(),
    };
}

// Command processing
rl.on("line", (line) => {
    const command = line.trim();

    if (command === "create_wallet") {
        const wallet = createWallet();
        console.log(JSON.stringify(wallet)); // Send wallet data back to Python
    } else {
        console.error(`Unknown command: ${command}`);
    }
});
