require("@nomicfoundation/hardhat-ethers");
require("@nomicfoundation/hardhat-chai-matchers");
const path = require("path");
require("dotenv").config({ path: path.resolve(__dirname, "..", ".env") });

const { RPC_URL, PRIVATE_KEY, CHAIN_ID } = process.env;

// Only expose the public-testnet network when the user has actually configured it,
// so a missing RPC_URL can never break local development.
const publicNetworks = {};
if (RPC_URL && !RPC_URL.includes("127.0.0.1") && !RPC_URL.includes("localhost") && PRIVATE_KEY) {
  publicNetworks.sepolia = {
    url: RPC_URL,
    accounts: [PRIVATE_KEY],
    chainId: CHAIN_ID ? Number(CHAIN_ID) : 11155111,
  };
}

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  networks: {
    hardhat: { chainId: 31337 },
    localhost: { url: "http://127.0.0.1:8545", chainId: 31337 },
    ...publicNetworks,
  },
  paths: { sources: "./contracts", tests: "./test", cache: "./cache", artifacts: "./artifacts" },
};
