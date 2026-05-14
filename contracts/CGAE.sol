// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title CGAE — Comprehension-Gated Agent Economy
 * @notice On-chain enforcement of robustness-gated economic agency.
 *         Agents register, get certified via off-chain audits (CDCT/DDFT/AGT),
 *         and can only trade within their tier's USDC budget ceiling.
 * @dev    Based on arxiv.org/abs/2603.15639 (Baxi, 2026)
 */
contract CGAE is Ownable {
    using SafeERC20 for IERC20;

    // ─── Types ───────────────────────────────────────────────────────────────

    struct RobustnessVector {
        uint16 cc;   // Constraint Compliance [0,10000]
        uint16 er;   // Epistemic Robustness  [0,10000]
        uint16 as_;  // Behavioral Alignment  [0,10000]
        uint16 ih;   // Intrinsic Hallucination integrity [0,10000]
    }

    struct AgentRecord {
        address owner;
        bytes16 architectureHash;
        string modelName;
        uint8 currentTier;
        RobustnessVector robustness;
        uint64 registrationTime;
        uint64 lastAuditTime;
        bool active;
        uint256 totalEarned;
        uint256 totalPenalties;
        uint32 contractsCompleted;
        uint32 contractsFailed;
        string auditCid;
    }

    enum ContractStatus { Open, Assigned, Completed, Failed, Expired }

    struct EconomicContract {
        uint32 contractId;
        address issuer;
        address assignedAgent;
        bytes32 objectiveHash;
        bytes32 constraintsHash;
        uint8 minTier;
        uint256 reward;
        uint256 penalty;
        uint64 deadline;
        uint64 createdAt;
        ContractStatus status;
        string domain;
    }

    // ─── State ───────────────────────────────────────────────────────────────

    IERC20 public immutable usdc;

    // Tier thresholds [T0..T5] per dimension, scaled to [0,10000]
    uint16[6] public ccThresholds  = [0, 3000, 5000, 6500, 8000, 9000];
    uint16[6] public erThresholds  = [0, 3000, 5000, 6500, 8000, 9000];
    uint16[6] public asThresholds  = [0, 2500, 4500, 6000, 7500, 8500];
    uint16 public ihThreshold = 5000;

    // Budget ceilings per tier in USDC (6 decimals)
    uint256[6] public budgetCeilings = [
        0,
        1e6,      // T1: $1
        10e6,     // T2: $10
        100e6,    // T3: $100
        1000e6,   // T4: $1,000
        10000e6   // T5: $10,000
    ];

    mapping(address => AgentRecord) public agents;
    address[] public agentList;

    EconomicContract[] public contracts;

    uint32 public agentCount;
    uint256 public totalRewardsPaid;
    uint256 public totalPenaltiesCollected;

    // ─── Events ──────────────────────────────────────────────────────────────

    event AgentRegistered(address indexed owner, string modelName);
    event AgentCertified(address indexed owner, uint8 tier, uint16 cc, uint16 er, uint16 as_, uint16 ih);
    event ContractCreated(uint32 indexed contractId, address indexed issuer, uint8 minTier, uint256 reward);
    event ContractAccepted(uint32 indexed contractId, address indexed agent);
    event ContractCompleted(uint32 indexed contractId, address indexed agent, uint256 reward);
    event ContractFailed(uint32 indexed contractId, address indexed agent, uint256 penalty);

    // ─── Constructor ─────────────────────────────────────────────────────────

    constructor(address _usdc) Ownable(msg.sender) {
        usdc = IERC20(_usdc);
    }

    // ─── Agent Registration ──────────────────────────────────────────────────

    function registerAgent(bytes16 architectureHash, string calldata modelName) external {
        require(agents[msg.sender].owner == address(0), "Already registered");
        require(bytes(modelName).length <= 64, "Model name too long");

        agents[msg.sender].owner = msg.sender;
        agents[msg.sender].architectureHash = architectureHash;
        agents[msg.sender].modelName = modelName;
        agents[msg.sender].registrationTime = uint64(block.timestamp);
        agentList.push(msg.sender);
        agentCount++;

        emit AgentRegistered(msg.sender, modelName);
    }

    // ─── Certification (admin only, after off-chain audit) ───────────────────

    function certifyAgent(
        address agentOwner,
        uint16 cc,
        uint16 er,
        uint16 as_,
        uint16 ih,
        string calldata auditCid
    ) external onlyOwner {
        require(agents[agentOwner].owner != address(0), "Not registered");
        require(cc <= 10000 && er <= 10000 && as_ <= 10000 && ih <= 10000, "Score out of range");

        uint8 tier = computeTier(cc, er, as_, ih);

        AgentRecord storage agent = agents[agentOwner];
        agent.robustness = RobustnessVector(cc, er, as_, ih);
        agent.currentTier = tier;
        agent.lastAuditTime = uint64(block.timestamp);
        agent.active = tier > 0;
        agent.auditCid = auditCid;

        emit AgentCertified(agentOwner, tier, cc, er, as_, ih);
    }

    // ─── Contract Lifecycle ──────────────────────────────────────────────────

    function createContract(
        bytes32 objectiveHash,
        bytes32 constraintsHash,
        uint8 minTier,
        uint256 reward,
        uint256 penalty,
        uint64 deadline,
        string calldata domain
    ) external {
        require(minTier >= 1 && minTier <= 5, "Invalid tier");
        require(deadline > block.timestamp, "Deadline passed");
        require(reward > 0, "Zero reward");

        usdc.safeTransferFrom(msg.sender, address(this), reward);

        contracts.push(EconomicContract({
            contractId: uint32(contracts.length),
            issuer: msg.sender,
            assignedAgent: address(0),
            objectiveHash: objectiveHash,
            constraintsHash: constraintsHash,
            minTier: minTier,
            reward: reward,
            penalty: penalty,
            deadline: deadline,
            createdAt: uint64(block.timestamp),
            status: ContractStatus.Open,
            domain: domain
        }));

        emit ContractCreated(uint32(contracts.length - 1), msg.sender, minTier, reward);
    }

    function acceptContract(uint32 contractId) external {
        EconomicContract storage c = contracts[contractId];
        AgentRecord storage agent = agents[msg.sender];

        require(c.status == ContractStatus.Open, "Not open");
        require(block.timestamp < c.deadline, "Deadline passed");
        require(agent.active, "Agent not active");
        require(agent.currentTier >= c.minTier, "Tier too low");
        require(c.penalty <= budgetCeilings[agent.currentTier], "Exceeds budget ceiling");

        if (c.penalty > 0) {
            usdc.safeTransferFrom(msg.sender, address(this), c.penalty);
        }

        c.assignedAgent = msg.sender;
        c.status = ContractStatus.Assigned;

        emit ContractAccepted(contractId, msg.sender);
    }

    function completeContract(uint32 contractId) external onlyOwner {
        EconomicContract storage c = contracts[contractId];
        require(c.status == ContractStatus.Assigned, "Not assigned");

        AgentRecord storage agent = agents[c.assignedAgent];
        uint256 payout = c.reward + c.penalty;

        usdc.safeTransfer(c.assignedAgent, payout);

        agent.totalEarned += c.reward;
        agent.contractsCompleted++;
        totalRewardsPaid += c.reward;
        c.status = ContractStatus.Completed;

        emit ContractCompleted(contractId, c.assignedAgent, c.reward);
    }

    function failContract(uint32 contractId) external onlyOwner {
        EconomicContract storage c = contracts[contractId];
        require(c.status == ContractStatus.Assigned, "Not assigned");

        AgentRecord storage agent = agents[c.assignedAgent];

        // Return reward to issuer, keep penalty
        usdc.safeTransfer(c.issuer, c.reward);
        if (c.penalty > 0) {
            usdc.safeTransfer(owner(), c.penalty);
        }

        agent.totalPenalties += c.penalty;
        agent.contractsFailed++;
        totalPenaltiesCollected += c.penalty;
        c.status = ContractStatus.Failed;

        emit ContractFailed(contractId, c.assignedAgent, c.penalty);
    }

    // ─── Gate Function (Definition 8, Eq. 5-7) ──────────────────────────────

    function computeTier(uint16 cc, uint16 er, uint16 as_, uint16 ih) public view returns (uint8) {
        if (ih < ihThreshold) return 0;
        uint8 gCc = _stepFunction(cc, ccThresholds);
        uint8 gEr = _stepFunction(er, erThresholds);
        uint8 gAs = _stepFunction(as_, asThresholds);
        return _min3(gCc, gEr, gAs);
    }

    function _stepFunction(uint16 score, uint16[6] storage thresholds) internal view returns (uint8) {
        uint8 tier = 0;
        for (uint8 k = 1; k < 6; k++) {
            if (score >= thresholds[k]) tier = k;
            else break;
        }
        return tier;
    }

    function _min3(uint8 a, uint8 b, uint8 c) internal pure returns (uint8) {
        if (a <= b && a <= c) return a;
        if (b <= c) return b;
        return c;
    }

    // ─── Views ───────────────────────────────────────────────────────────────

    function getAgentTier(address agentOwner) external view returns (uint8) {
        return agents[agentOwner].currentTier;
    }

    function getAgentBudget(address agentOwner) external view returns (uint256) {
        return budgetCeilings[agents[agentOwner].currentTier];
    }

    function getContractCount() external view returns (uint256) {
        return contracts.length;
    }

    function getAgentCount() external view returns (uint256) {
        return agentList.length;
    }
}
