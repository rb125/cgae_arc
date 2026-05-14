"""
LLM Agent — AWS Bedrock via boto3 Converse API.

Auth: boto3 automatically picks up the AWS_BEARER_TOKEN_BEDROCK env var.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import boto3

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0


def call_with_retry(api_call, config: RetryConfig, log_prefix: str = ""):
    retries = 0
    while True:
        try:
            return api_call()
        except Exception as e:
            retries += 1
            if retries > config.max_retries:
                logger.error(f"{log_prefix} Final attempt failed: {e}")
                raise
            delay = min(config.max_delay, config.base_delay * (2 ** (retries - 1)))
            logger.warning(f"{log_prefix} Attempt {retries}/{config.max_retries} failed: {e}. Retrying in {delay:.1f}s...")
            time.sleep(delay)


_bedrock_clients: dict[str, object] = {}


def _get_bedrock_client(region: str):
    if region not in _bedrock_clients:
        _bedrock_clients[region] = boto3.client("bedrock-runtime", region_name=region)
    return _bedrock_clients[region]


class LLMAgent:
    """Bedrock-backed LLM agent. Uses AWS_BEARER_TOKEN_BEDROCK env var for auth."""

    def __init__(self, model_config: dict):
        self.model_name: str = model_config["model_name"]
        self.model_id: str = model_config["model_id"]
        self.provider: str = model_config["provider"]
        self.family: str = model_config.get("family", "Unknown")
        self.region: str = model_config.get("region", "us-east-1")
        self.retry_config = RetryConfig()

        self.total_calls: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_errors: int = 0
        self.total_latency_ms: float = 0.0

        if not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
            raise EnvironmentError("Missing env var AWS_BEARER_TOKEN_BEDROCK")

        self._client = _get_bedrock_client(self.region)

    def chat(self, messages: list[dict]) -> str:
        """Send messages to Bedrock Converse API and return response text."""
        log_prefix = f"[{self.model_name}]"

        def _call():
            bedrock_msgs = []
            system_parts = []
            for m in messages:
                if m["role"] == "system":
                    system_parts.append({"text": m["content"]})
                else:
                    bedrock_msgs.append({
                        "role": m["role"],
                        "content": [{"text": m["content"]}],
                    })

            kwargs = {
                "modelId": self.model_id,
                "messages": bedrock_msgs,
                "inferenceConfig": {"temperature": 0.0, "maxTokens": 4096},
            }
            if system_parts:
                kwargs["system"] = system_parts

            start = time.time()
            response = self._client.converse(**kwargs)
            latency = (time.time() - start) * 1000

            self.total_calls += 1
            self.total_latency_ms += latency
            usage = response.get("usage", {})
            self.total_input_tokens += usage.get("inputTokens", 0)
            self.total_output_tokens += usage.get("outputTokens", 0)

            content = response["output"]["message"]["content"]
            for block in content:
                if "text" in block:
                    return block["text"]
            return str(content)

        try:
            return call_with_retry(_call, self.retry_config, log_prefix)
        except Exception:
            self.total_errors += 1
            raise

    def execute_task(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def usage_summary(self) -> dict:
        return {
            "model": self.model_name,
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_errors": self.total_errors,
            "avg_latency_ms": self.total_latency_ms / max(self.total_calls, 1),
        }

    def __repr__(self):
        return f"LLMAgent({self.model_name}, bedrock/{self.region})"


def create_llm_agent(model_config: dict) -> LLMAgent:
    return LLMAgent(model_config)


def create_llm_agents(model_configs: list[dict]) -> dict[str, LLMAgent]:
    agents = {}
    for config in model_configs:
        try:
            agent = create_llm_agent(config)
            agents[agent.model_name] = agent
            logger.info(f"Created LLM agent: {agent}")
        except Exception as e:
            logger.warning(f"Skipping {config['model_name']}: {e}")
    return agents
