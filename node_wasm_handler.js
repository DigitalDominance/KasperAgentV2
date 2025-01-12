globalThis.WebSocket = require("websocket").w3cwebsocket;

const express = require("express");
const bodyParser = require("body-parser");
const helmet = require("helmet");

const kaspa = require("./wasm/kaspa");
const { RpcClient, Resolver, Mnemonic, XPrv, NetworkType } = kaspa;

const app = express();
app.use(bodyParser.json());
app.use(helmet());

const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

rpc.connect().then(() => console.log("RPC connected successfully!")).catch(err => {
    console.error("RPC connection failed:", err.message);
});


app.post("/execute", async (req, res) => {
    const { command, args } = req.body;

    try {
        await connectRpc();

        switch (command) {
            case "createWallet":
                const mnemonic = Mnemonic.random();
                const seed = mnemonic.toSeed();
                const xPrv = new XPrv(seed);
                const receivePath = "m/44'/111111'/0'/0/0";
                const receiveKey = xPrv.derivePath(receivePath).toXPub().toPublicKey();
                const receiveAddress = receiveKey.toAddress(NetworkType.Mainnet);
                const changePath = "m/44'/111111'/0'/1/0";
                const changeKey = xPrv.derivePath(changePath).toXPub().toPublicKey();
                const changeAddress = changeKey.toAddress(NetworkType.Mainnet);
                res.json({
                    success: true,
                    mnemonic: mnemonic.phrase,
                    receivingAddress: receiveAddress.toString(),
                    changeAddress: changeAddress.toString(),
                    xPrv: xPrv.intoString("xprv"),
                });
                break;
            case "getBalance":
                const { balances } = await rpc.getBalancesByAddresses({ addresses: [args[0]] });
                res.json({ success: true, balance: balances[0]?.amount.toString() || "0" });
                break;
            default:
                res.status(400).json({ success: false, error: "Invalid command" });
        }
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

const PORT = 3000;
app.listen(PORT, () => console.log(`Node.js WASM server running on port ${PORT}`));
