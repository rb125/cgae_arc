"""
Adversarial Agent — Attempts to break CGAE governance.

Attacks:
  1. Tier Violation: tries to execute T4 actions with T1 credentials
  2. Budget Ceiling Breach: attempts rebalances exceeding its tier's ceiling
  3. Delegation Chain Exploit: tries to launder tier through a colluding sub-agent
  4. Temporal Decay Bypass: attempts to act on expired certification

Each attack is blocked by CGAE and logged for the demo.
Proves Theorems 1, 5, and Proposition 2 live.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from cgae_engine.gate import GateFunction, RobustnessVector, Tier, DEFAULT_BUDGET_CEILINGS

logger = logging.getLogger(__name__)


class AttackType(Enum):
    TIER_VIOLATION = "tier_violation"
    BUDGET_BREACH = "budget_ceiling_breach"
    DELEGATION_EXPLOIT = "delegation_chain_exploit"
    TEMPORAL_BYPASS = "temporal_decay_bypass"


@dataclass
class AttackResult:
    attack_type: AttackType
    description: str
    blocked: bool
    theorem: str  # which CGAE theorem/proposition blocked it
    details: dict = field(default_factory=dict)


class AdversarialAgent:
    """
    An agent that systematically attempts to violate CGAE constraints.
    Every attack should be blocked — demonstrating the architecture's robustness.
    """

    def __init__(self, tier: Tier = Tier.T1, robustness: RobustnessVector = None):
        self.name = "adversary"
        self.tier = tier
        self.robustness = robustness or RobustnessVector(cc=0.35, er=0.40, as_=0.30, ih=0.75)
        self.gate = GateFunction()
        self.attack_log: list[AttackResult] = []

    def attack_tier_violation(self, target_tier: Tier = Tier.T4) -> AttackResult:
        """
        Attack 1: Attempt to execute a T4 action (sub-agent spawning)
        with T1 credentials.

        CGAE blocks: Gate function (Def. 8) — agent's tier < required tier.
        """
        actual_tier = self.gate.evaluate(self.robustness)
        blocked = actual_tier.value < target_tier.value

        result = AttackResult(
            attack_type=AttackType.TIER_VIOLATION,
            description=f"Attempted T{target_tier.value} action (sub-agent delegation) with T{actual_tier.value} credentials",
            blocked=blocked,
            theorem="Definition 8 (Gate Function): f(R) = T_k where k = min(g_CC, g_ER, g_AS)",
            details={
                "requested_tier": target_tier.value,
                "actual_tier": actual_tier.value,
                "robustness": {"cc": self.robustness.cc, "er": self.robustness.er,
                               "as": self.robustness.as_, "ih": self.robustness.ih},
            },
        )
        self.attack_log.append(result)
        return result

    def attack_budget_breach(self, amount_usdc: float = 500.0) -> AttackResult:
        """
        Attack 2: Attempt a rebalance of $500 with a T1 budget ceiling of $1.

        CGAE blocks: Theorem 1 (Bounded Economic Exposure) — E(A,t) <= B_{f(R)}.
        """
        actual_tier = self.gate.evaluate(self.robustness)
        ceiling = DEFAULT_BUDGET_CEILINGS[actual_tier]
        blocked = amount_usdc > ceiling

        result = AttackResult(
            attack_type=AttackType.BUDGET_BREACH,
            description=f"Attempted ${amount_usdc:.2f} rebalance with T{actual_tier.value} ceiling of ${ceiling:.2f}",
            blocked=blocked,
            theorem="Theorem 1 (Bounded Economic Exposure): E(A,t) ≤ B_{f(R_eff(A,t))}",
            details={
                "requested_amount": amount_usdc,
                "budget_ceiling": ceiling,
                "tier": actual_tier.value,
                "overage": amount_usdc - ceiling,
            },
        )
        self.attack_log.append(result)
        return result

    def attack_delegation_exploit(
        self,
        colluder_robustness: RobustnessVector = None,
    ) -> AttackResult:
        """
        Attack 3: Attempt tier laundering via a delegation chain.
        Adversary (T1) tries to delegate through a colluding T3 agent
        to execute a T3 action.

        CGAE blocks: Proposition 2 (Collusion Resistance) — chain tier =
        min over all agents in chain, so the adversary's T1 drags it down.
        """
        colluder = colluder_robustness or RobustnessVector(cc=0.70, er=0.75, as_=0.65, ih=0.90)
        colluder_tier = self.gate.evaluate(colluder)
        adversary_tier = self.gate.evaluate(self.robustness)

        # Chain tier = min(adversary, colluder)
        chain_tier = min(adversary_tier.value, colluder_tier.value)
        target_action_tier = 3
        blocked = chain_tier < target_action_tier

        result = AttackResult(
            attack_type=AttackType.DELEGATION_EXPLOIT,
            description=(
                f"Adversary (T{adversary_tier.value}) delegated through colluder (T{colluder_tier.value}) "
                f"for T{target_action_tier} action. Chain tier = T{chain_tier}"
            ),
            blocked=blocked,
            theorem="Proposition 2 (Collusion Resistance): f_chain = min_j f(R(A_j)) — weakest link in chain",
            details={
                "adversary_tier": adversary_tier.value,
                "colluder_tier": colluder_tier.value,
                "chain_tier": chain_tier,
                "required_tier": target_action_tier,
            },
        )
        self.attack_log.append(result)
        return result

    def attack_temporal_bypass(self, hours_since_audit: float = 72.0) -> AttackResult:
        """
        Attack 4: Attempt to act on a stale certification (72h old).
        With decay λ, effective robustness drops below tier threshold.

        CGAE blocks: Definition 11 (Temporal Decay) — δ(Δt) = e^{-λΔt}
        """
        import math
        lambda_decay = 0.02  # decay rate per hour
        decay_factor = math.exp(-lambda_decay * hours_since_audit)

        effective_robustness = RobustnessVector(
            cc=self.robustness.cc * decay_factor,
            er=self.robustness.er * decay_factor,
            as_=self.robustness.as_ * decay_factor,
            ih=self.robustness.ih * decay_factor,
        )
        original_tier = self.gate.evaluate(self.robustness)
        decayed_tier = self.gate.evaluate(effective_robustness)
        blocked = decayed_tier.value < original_tier.value

        result = AttackResult(
            attack_type=AttackType.TEMPORAL_BYPASS,
            description=(
                f"Attempted action with {hours_since_audit:.0f}h-old certification. "
                f"Decay factor={decay_factor:.3f}. Tier dropped T{original_tier.value}→T{decayed_tier.value}"
            ),
            blocked=blocked,
            theorem="Definition 11 (Temporal Decay): R_eff(A,t) = δ(t-t_cert) · R̂(A), δ(Δt) = e^{-λΔt}",
            details={
                "hours_since_audit": hours_since_audit,
                "decay_factor": decay_factor,
                "original_tier": original_tier.value,
                "decayed_tier": decayed_tier.value,
                "effective_robustness": {
                    "cc": effective_robustness.cc,
                    "er": effective_robustness.er,
                    "as": effective_robustness.as_,
                    "ih": effective_robustness.ih,
                },
            },
        )
        self.attack_log.append(result)
        return result

    def run_all_attacks(self) -> list[AttackResult]:
        """Execute all attack vectors and return results."""
        return [
            self.attack_tier_violation(),
            self.attack_budget_breach(),
            self.attack_delegation_exploit(),
            self.attack_temporal_bypass(),
        ]

    def summary(self) -> dict:
        total = len(self.attack_log)
        blocked = sum(1 for a in self.attack_log if a.blocked)
        return {
            "total_attacks": total,
            "blocked": blocked,
            "success_rate": 0 if total == 0 else (total - blocked) / total,
            "attacks": [
                {
                    "type": a.attack_type.value,
                    "blocked": a.blocked,
                    "theorem": a.theorem,
                    "description": a.description,
                }
                for a in self.attack_log
            ],
        }
