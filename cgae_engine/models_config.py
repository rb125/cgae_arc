"""
CGAE Model Configurations — Arc x Circle Hackathon

Trading agents backed by AWS Bedrock models. Each model competes in the
CGAE economy on Arc, gated by robustness audits (CDCT/DDFT/AGT).

Environment variables required:
  AWS_ACCESS_KEY_ID          - AWS credentials for Bedrock
  AWS_SECRET_ACCESS_KEY      - AWS credentials for Bedrock
  AWS_REGION                 - Bedrock region (default: us-east-1)
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
        "model_name": "claude-sonnet-4",
        "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "provider": "bedrock",
        "region": "us-east-1",
        "architecture": "dense",
        "family": "Anthropic",
        "tier_assignment": "contestant",
    },
    {
        "model_name": "claude-haiku",
        "model_id": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "provider": "bedrock",
        "region": "us-east-1",
        "architecture": "dense",
        "family": "Anthropic",
        "tier_assignment": "contestant",
    },
]

# Jury model for output verification during audits
JURY_MODELS = [
    {
        "model_name": "claude-sonnet-4-jury",
        "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "provider": "bedrock",
        "region": "us-east-1",
        "architecture": "dense",
        "family": "Anthropic",
        "tier_assignment": "jury",
    },
]

CONTESTANT_MODELS = [m for m in AVAILABLE_MODELS if m["tier_assignment"] == "contestant"]


def get_model_config(model_name: str) -> dict:
    """Look up a model config by name."""
    for m in AVAILABLE_MODELS + JURY_MODELS:
        if m["model_name"] == model_name:
            return m
    raise KeyError(f"Model '{model_name}' not found in AVAILABLE_MODELS")
