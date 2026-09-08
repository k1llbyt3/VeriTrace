/**
 * Shared ethers.js plumbing for the standalone register/verify CLIs.
 * These run with plain `node` (not `hardhat run`) so the Python pipeline can
 * call them and read one JSON object from stdout. Human-readable progress goes
 * to stderr so it never pollutes that JSON.
 */
const fs = require("fs");
const path = require("path");
const { ethers } = require("ethers");

const ROOT = path.resolve(__dirname, "..", "..");
require("dotenv").config({ path: path.join(ROOT, ".env") });

const ARTIFACT = path.join(
  __dirname,
  "..",
  "artifacts",
  "contracts",
  "ContentRegistry.sol",
  "ContentRegistry.json"
);

function loadAbi() {
  if (!fs.existsSync(ARTIFACT)) {
    throw new Error("contract not compiled yet - run: npx hardhat compile (inside blockchain/)");
  }
  return JSON.parse(fs.readFileSync(ARTIFACT, "utf8")).abi;
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (token.startsWith("--")) {
      const key = token.slice(2);
      const next = argv[i + 1];
      if (next && !next.startsWith("--")) {
        args[key] = next;
        i += 1;
      } else {
        args[key] = true;
      }
    }
  }
  return args;
}

function resolveAddress(explicit, chainId) {
  if (explicit) return explicit;
  if (process.env.CONTRACT_ADDRESS) return process.env.CONTRACT_ADDRESS;
  const dir = path.join(__dirname, "..", "deployments");
  if (fs.existsSync(dir)) {
    for (const file of fs.readdirSync(dir)) {
      const info = JSON.parse(fs.readFileSync(path.join(dir, file), "utf8"));
      if (Number(info.chainId) === Number(chainId)) return info.address;
    }
  }
  throw new Error(
    "no contract address - deploy first, or set CONTRACT_ADDRESS in .env, or pass --address"
  );
}

/** Connect to the chain and return { provider, signer, network }. */
async function connect({ readOnly = false } = {}) {
  const rpcUrl = process.env.RPC_URL || "http://127.0.0.1:8545";
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  let network;
  try {
    network = await provider.getNetwork();
  } catch (error) {
    throw new Error(
      `cannot reach the blockchain at ${rpcUrl} - is the node running? (${error.shortMessage || error.message})`
    );
  }
  let signer = null;
  if (!readOnly) {
    if (process.env.PRIVATE_KEY) {
      signer = new ethers.Wallet(process.env.PRIVATE_KEY, provider);
    } else {
      // local dev nodes expose unlocked test accounts, so no key is needed
      signer = await provider.getSigner(0);
    }
  }
  return { provider, signer, network, rpcUrl };
}

async function getContract({ readOnly = false, address } = {}) {
  const { provider, signer, network, rpcUrl } = await connect({ readOnly });
  const resolved = resolveAddress(address, network.chainId);
  const contract = new ethers.Contract(resolved, loadAbi(), readOnly ? provider : signer);
  return { contract, provider, signer, network, address: resolved, rpcUrl };
}

/** Print the machine-readable result and exit. */
function emit(payload, exitCode = 0) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
  process.exitCode = exitCode;
}

function fail(message) {
  emit({ ok: false, error: String(message) }, 1);
}

module.exports = { ethers, parseArgs, getContract, connect, loadAbi, emit, fail };
