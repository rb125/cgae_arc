# CGAE on Arc — Comprehension-Gated Perps Trading Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Solidity](https://img.shields.io/badge/Solidity-^0.8.20-363636.svg)](contracts/)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![Hardhat](https://img.shields.io/badge/Built%20with-Hardhat-orange.svg)](https://hardhat.org)

**Arc × Circle Hackathon | RFB 01 — Perpetual Futures Trading Agent**

AI trading agents whose leverage, position size, and autonomy are dynamically gated by verified robustness — not just capability benchmarks.

## Architecture

```
AWS Bedrock (Nova Pro, Claude Sonnet, Claude Haiku)
        │ trading decisions
        ▼
┌─────────────────────────────────┐
│  CGAE Engine (Python)           │
│  • Gate function (weakest-link) │
│  • Audit orchestration          │
│  • Temporal decay               │
│  • Trading strategy             │
└────────────┬────────────────────┘
             │ certify / trade
             ▼
┌─────────────────────────────────┐
│  Arc Chain (EVM)                │
│  • CGAE.sol (tiers + budgets)   │
│  • USDC escrow + settlement     │
│  • Circle Paymaster (gas=USDC)  │
│  • USYC (idle capital yield)    │
└─────────────────────────────────┘
             │ audits
             ▼
┌─────────────────────────────────┐
│  Robustness APIs (Vercel)       │
│  • CDCT — constraint compliance │
│  • DDFT — epistemic robustness  │
│  • AGT  — behavioral alignment  │
└─────────────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/<your-username>/cgae.git && cd cgae

# Python dependencies
pip install -r requirements.txt

# Solidity dependencies
npm install

# Compile contracts
npx hardhat compile

# Run tests
npx hardhat test

# Environment
cp .env.example .env
# Fill in: AWS credentials, Arc RPC, Circle API key
```

## Project Structure

```
contracts/       Solidity smart contracts (CGAE.sol)
agents/          Python trading & adversarial agents
cgae_engine/     Core gate logic, audit orchestration, LLM integration
scripts/         Deployment & demo scripts
dashboard/       Next.js monitoring dashboard
test/            Hardhat test suite
```

## Paper

Based on: [The Comprehension-Gated Agent Economy](https://arxiv.org/abs/2603.15639) (Baxi, 2026)

## License

[MIT](LICENSE)
