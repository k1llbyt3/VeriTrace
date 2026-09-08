/**
 * Deploys ContentRegistry and writes the address to blockchain/deployments/<network>.json
 * so the Python pipeline can find it without anyone copying strings by hand.
 *
 * Local:   npx hardhat run scripts/deploy.js --network localhost
 * Sepolia: npx hardhat run scripts/deploy.js --network sepolia
 */
const fs = require("fs");
const path = require("path");
const { ethers, network } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`Network  : ${network.name} (chainId ${network.config.chainId})`);
  console.log(`Deployer : ${deployer.address}`);
  console.log(`Balance  : ${ethers.formatEther(balance)} ETH`);

  const factory = await ethers.getContractFactory("ContentRegistry");
  const registry = await factory.deploy();
  console.log("Deploying ContentRegistry...");
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  const receipt = await registry.deploymentTransaction().wait();

  const info = {
    network: network.name,
    chainId: Number(network.config.chainId),
    contract: "ContentRegistry",
    address,
    deployer: deployer.address,
    txHash: receipt.hash,
    blockNumber: receipt.blockNumber,
    deployedAt: new Date().toISOString(),
  };

  const dir = path.join(__dirname, "..", "deployments");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, `${network.name}.json`), JSON.stringify(info, null, 2));

  console.log(`\nContentRegistry deployed at : ${address}`);
  console.log(`Deployment tx               : ${receipt.hash}`);
  console.log(`Block                       : ${receipt.blockNumber}`);
  console.log(`\nAdd this line to your .env file:`);
  console.log(`CONTRACT_ADDRESS=${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
