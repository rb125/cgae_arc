# CGAE on Arc — Comprehension-Gated Perps Trading Agent

**Arc x Circle Hackathon | RFB 01 — Perpetual Futures Trading Agent**

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

## Setup

```bash
# Python
pip install -r requirements.txt

# Solidity
npm install
npx hardhat compile

# Environment
cp .env.example .env
# Fill in AWS credentials, Arc RPC, Circle API key
```

## Paper

Based on: [The Comprehension-Gated Agent Economy](https://arxiv.org/abs/2603.15639) (Baxi, 2026)
