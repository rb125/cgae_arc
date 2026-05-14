import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  networks: {
    arc: {
      url: process.env.ARC_RPC_URL || "https://rpc.arc.network",
      accounts: process.env.ARC_PRIVATE_KEY ? [process.env.ARC_PRIVATE_KEY] : [],
    },
  },
};

export default config;
