"""
CGAE Model Configurations — Arc x Circle Hackathon

Trading agents backed by AWS Bedrock models with real CDCT/DDFT/AGT scores.
model_name must match the name used in the framework APIs for score lookups.

Auth: Set AWS_BEARER_TOKEN_BEDROCK env var with your Bedrock API key.
"""

AVAILABLE_MODELS = [
    {
        "model_name": "nova-pro",
        "model_id": "amazon.nova-pro-v1:0",
        "provider": "bedrock",
        "region": "us-east-1",
        "architecture": "dense",
        "family": "Amazon",
        "tier_assignment": "contestant",
    },
    {
        "model_name": "DeepSeek-V3.2",
        "model_id": "deepseek.v3.2",
        "provider": "bedrock",
        "region": "us-east-1",
        "architecture": "mixture-of-experts",
        "family": "DeepSeek",
        "tier_assignment": "contestant",
    },
    {
        "model_name": "Kimi-K2.5",
        "model_id": "moonshotai.kimi-k2.5",
        "provider": "bedrock",
        "region": "us-east-1",
        "architecture": "dense",
        "family": "Moonshot",
        "tier_assignment": "contestant",
    },
    {
        "model_name": "MiniMax-M2.5",
        "model_id": "minimax.minimax-m2.5",
        "provider": "bedrock",
        "region": "us-east-1",
        "architecture": "dense",
        "family": "MiniMax",
        "tier_assignment": "adversary",
    },
]

# Jury model for output verification during audits
JURY_MODELS = [
    {
        "model_name": "Kimi-K2.5-jury",
        "model_id": "moonshotai.kimi-k2.5",
        "provider": "bedrock",
        "region": "us-east-1",
        "architecture": "dense",
        "family": "Moonshot",
        "tier_assignment": "jury",
    },
]

CONTESTANT_MODELS = [m for m in AVAILABLE_MODELS if m["tier_assignment"] != "jury"]


def get_model_config(model_name: str) -> dict:
    """Look up a model config by name."""
    for m in AVAILABLE_MODELS + JURY_MODELS:
        if m["model_name"] == model_name:
            return m
    raise KeyError(f"Model '{model_name}' not found in AVAILABLE_MODELS")
