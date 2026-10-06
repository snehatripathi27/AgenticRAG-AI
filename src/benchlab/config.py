"""Strict configuration shared by the CLI and API."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["demo", "hf", "vllm", "api"] = "demo"
    name: str = Field(default="demo-baseline", min_length=1, max_length=200)
    revision: str | None = None
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = Field(default="OPENAI_API_KEY", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    device: str = "auto"
    max_tokens: int = Field(default=64, ge=1, le=4096)
    temperature: float = Field(default=0, ge=0, le=2)
    timeout: float = Field(default=60, gt=0, le=600)

    @field_validator("base_url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("base_url must be HTTP(S) without credentials, query, or fragment")
        return value.rstrip("/")


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Untitled evaluation", min_length=1, max_length=100)
    model: ModelConfig = Field(default_factory=ModelConfig)
    tasks: list[str] = Field(
        default_factory=lambda: ["demo_reasoning", "demo_math", "demo_knowledge"], min_length=1, max_length=30
    )
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    limit: int = Field(default=20, ge=1, le=100000)
    batch_size: int = Field(default=4, ge=1, le=128)
    prompts: dict[str, str] = Field(default_factory=dict)
    dataset_revisions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_tasks(self):
        if len(set(self.tasks)) != len(self.tasks):
            raise ValueError("tasks must be unique")
        if set(self.prompts) - set(self.tasks) or set(self.dataset_revisions) - set(self.tasks):
            raise ValueError("prompt and revision overrides must refer to selected tasks")
        return self


def load_config(path: Path) -> RunConfig:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML/JSON mapping")  # noqa: TRY004
    return RunConfig.model_validate(data)
