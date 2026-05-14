import { expect } from "chai";
import { ethers } from "hardhat";

describe("CGAE", function () {
  async function deploy() {
    const [owner, agent1, agent2, issuer] = await ethers.getSigners();

    // Deploy mock USDC (6 decimals)
    const MockERC20 = await ethers.getContractFactory("MockUSDC");
    const usdc = await MockERC20.deploy();

    const CGAE = await ethers.getContractFactory("CGAE");
    const cgae = await CGAE.deploy(await usdc.getAddress());

    // Mint USDC to participants
    await usdc.mint(issuer.address, 10000e6);
    await usdc.mint(agent1.address, 1000e6);
    await usdc.connect(issuer).approve(await cgae.getAddress(), 10000e6);
    await usdc.connect(agent1).approve(await cgae.getAddress(), 1000e6);

    return { cgae, usdc, owner, agent1, agent2, issuer };
  }

  describe("Gate Function", function () {
    it("computes correct tier from robustness vector", async function () {
      const { cgae } = await deploy();
      // CC=7000, ER=8000, AS=6000, IH=9000 → g_cc=3, g_er=3, g_as=3 → T3
      expect(await cgae.computeTier(7000, 8000, 6000, 9000)).to.equal(3);
    });

    it("weakest-link: low CC drags tier down", async function () {
      const { cgae } = await deploy();
      // CC=4000, ER=9000, AS=9000, IH=9000 → g_cc=1, g_er=5, g_as=5 → T1
      expect(await cgae.computeTier(4000, 9000, 9000, 9000)).to.equal(1);
    });

    it("IH below threshold forces T0", async function () {
      const { cgae } = await deploy();
      expect(await cgae.computeTier(9000, 9000, 9000, 4000)).to.equal(0);
    });
  });

  describe("Agent Lifecycle", function () {
    it("register → certify → check tier and budget", async function () {
      const { cgae, owner, agent1 } = await deploy();

      await cgae.connect(agent1).registerAgent("0x" + "ab".repeat(16), "nova-pro");
      expect(await cgae.getAgentTier(agent1.address)).to.equal(0);

      // Admin certifies after audit
      await cgae.connect(owner).certifyAgent(agent1.address, 7000, 8000, 6000, 9000, "QmAuditCID123");
      expect(await cgae.getAgentTier(agent1.address)).to.equal(3);
      expect(await cgae.getAgentBudget(agent1.address)).to.equal(100e6); // $100 USDC
    });
  });

  describe("Contract Lifecycle", function () {
    it("create → accept → complete (full flow)", async function () {
      const { cgae, usdc, owner, agent1, issuer } = await deploy();

      // Setup agent at T3
      await cgae.connect(agent1).registerAgent("0x" + "ab".repeat(16), "nova-pro");
      await cgae.connect(owner).certifyAgent(agent1.address, 7000, 8000, 6000, 9000, "QmCID");

      // Issuer creates contract
      await cgae.connect(issuer).createContract(
        ethers.zeroPadValue("0x01", 32),
        ethers.zeroPadValue("0x02", 32),
        2,       // minTier = T2
        50e6,    // reward = $50
        10e6,    // penalty = $10
        Math.floor(Date.now() / 1000) + 3600,
        "perps"
      );

      // Agent accepts (deposits penalty)
      const balBefore = await usdc.balanceOf(agent1.address);
      await cgae.connect(agent1).acceptContract(0);
      expect(await usdc.balanceOf(agent1.address)).to.equal(balBefore - BigInt(10e6));

      // Admin marks complete → agent gets reward + penalty back
      await cgae.connect(owner).completeContract(0);
      expect(await usdc.balanceOf(agent1.address)).to.equal(balBefore + BigInt(50e6));
    });

    it("rejects agent with tier too low", async function () {
      const { cgae, owner, agent1, issuer } = await deploy();

      await cgae.connect(agent1).registerAgent("0x" + "ab".repeat(16), "haiku");
      await cgae.connect(owner).certifyAgent(agent1.address, 4000, 4000, 4000, 9000, "QmCID");
      // Agent is T1

      await cgae.connect(issuer).createContract(
        ethers.zeroPadValue("0x01", 32),
        ethers.zeroPadValue("0x02", 32),
        3, 50e6, 10e6,
        Math.floor(Date.now() / 1000) + 3600,
        "perps"
      );

      await expect(cgae.connect(agent1).acceptContract(0)).to.be.revertedWith("Tier too low");
    });

    it("rejects penalty exceeding budget ceiling", async function () {
      const { cgae, usdc, owner, agent1, issuer } = await deploy();

      await cgae.connect(agent1).registerAgent("0x" + "ab".repeat(16), "haiku");
      // T1 agent: budget ceiling = $1
      await cgae.connect(owner).certifyAgent(agent1.address, 4000, 4000, 4000, 9000, "QmCID");

      await cgae.connect(issuer).createContract(
        ethers.zeroPadValue("0x01", 32),
        ethers.zeroPadValue("0x02", 32),
        1, 50e6, 5e6, // penalty $5 > T1 ceiling $1
        Math.floor(Date.now() / 1000) + 3600,
        "perps"
      );

      await expect(cgae.connect(agent1).acceptContract(0)).to.be.revertedWith("Exceeds budget ceiling");
    });
  });
});
