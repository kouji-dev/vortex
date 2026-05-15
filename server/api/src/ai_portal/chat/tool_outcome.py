from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolCallOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    provider: str
    input: dict = Field(default_factory=dict)
    result_snippet: str | None = None
    error: str | None = None
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
    # KB-specific per-chunk metadata (only populated for `search_knowledge_base`).
    chunks_meta: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _result_xor_error(self) -> Self:
        if self.result_snippet is None and self.error is None:
            raise ValueError("ToolCallOutcome must have result_snippet or error")
        return self
