globalThis.WebSocket = require("websocket").w3cwebsocket;

const express = require("express");
const bodyParser = require("body-parser");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");
require("dotenv").config();

const kaspa = require("./wasm/kaspa");
const { RpcClient, Resolver, Mnemonic, XPrv, NetworkType } = kaspa;

// Initialize Express app
const app = express();
app.use(bodyParser.json({ limit: "1mb" })); // Limit JSON body size to prevent abuse
app.use(helmet());

// Rate limiter middleware (e.g., max 100 requests per minute per IP)
const limiter = rateLimit({
    windowMs: 60 * 1000, // 1 minute
    max: 100, // Limit each IP to 100 requests per `windowMs`
    message: { success: false, error: "Too many requests, please try again later." },
});
app.use(limiter);

// Retrieve environment variables
const PORT = process.env.PORT;
const API_KEY = process.env.API_KEY;

// Middleware to validate API key
app.use((req, res, next) => {
    const clientApiKey = req.headers["x-api-key"];
    if (!clientApiKey || clientApiKey !== API_KEY) {
        return res.status(403).json({ success: false, error: "Forbidden: Invalid API Key" });
    }
    next();
});

// Initialize RPC client
const rpc = new RpcClient({
    resolver: new Resolver(),
    networkId: "mainnet",
});

rpc.connect()
    .then(() => console.log("RPC connected successfully!"))
    .catch((err) => {
        console.error("RPC connection failed:", err.message);
        process.exit(1); // Exit if the RPC connection fails
    });

// Endpoint to handle commands
app.post("/execute", async (req, res) => {
    const { command, args = [] } = req.body;

    try {
        console.log(`Received command: ${command}, Args: ${JSON.stringify(args)}`);

        switch (command) {
            case "createWallet": {
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
            }

            case "getBalance": {
                if (!args[0]) {
                    throw new Error("Address is required for 'getBalance'");
                }

                const { balances } = await rpc.getBalancesByAddresses({ addresses: [args[0]] });
                res.json({
                    success: true,
                    balance: balances[0]?.amount.toString() || "0",
                });
                break;
            }

            default:
                res.status(400).json({
                    success: false,
                    error: `Invalid command: ${command}`,
                });
                break;
        }
    } catch (err) {
        console.error(`Error executing command '${command}':`, err.message);
        res.status(500).json({
            success: false,
            error: err.message || "Internal Server Error",
        });
    }
});

// Start the server
app.listen(PORT, () => console.log(`Node.js WASM server running on port ${PORT}`));
