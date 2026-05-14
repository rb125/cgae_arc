"""CGAE Engine — Comprehension-Gated Agent Economy on Arc."""

from .gate import GateFunction, RobustnessVector, Tier, DEFAULT_BUDGET_CEILINGS
from .llm_agent import LLMAgent, create_llm_agent, create_llm_agents
from .models_config import AVAILABLE_MODELS, CONTESTANT_MODELS, JURY_MODELS, get_model_config
from .framework_clients import CDCTClient, DDFTClient, EECTClient
