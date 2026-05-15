import { ethers } from "hardhat";

async function main() {
  const USDC_ADDRESS = "0x3600000000000000000000000000000000000000";

  console.log("Deploying CGAE to Arc Testnet...");
  console.log("USDC address:", USDC_ADDRESS);

  const [deployer] = await ethers.getSigners();
  console.log("Deployer:", deployer.address);

  const balance = await ethers.provider.getBalance(deployer.address);
  console.log("Balance:", ethers.formatUnits(balance, 18), "USDC");

  const CGAE = await ethers.getContractFactory("CGAE");
  const cgae = await CGAE.deploy(USDC_ADDRESS);
  await cgae.waitForDeployment();

  const address = await cgae.getAddress();
  console.log("\n✅ CGAE deployed to:", address);
  console.log("\nAdd to .env:");
  console.log(`CGAE_CONTRACT_ADDRESS=${address}`);
  console.log(`USDC_CONTRACT_ADDRESS=${USDC_ADDRESS}`);
  console.log(`\nExplorer: https://testnet.arcscan.app/address/${address}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
