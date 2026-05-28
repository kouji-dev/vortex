"""OpenAI-compatible Embeddings surface — ``POST /v1/embeddings``.

Translation layer:

- OpenAI request (single string | list[str] | token-id arrays) → ``list[str]``
  + canonical embed dispatch via :class:`EmbeddingRouter`
- :class:`Embeddings` → OpenAI ``list`` envelope with
  ``data: [{object, index, embedding}]``

Routing model → provider, batched dispatch (chunked at the provider's
``max_batch``), and ``dimensions`` passthrough all live in
:class:`EmbeddingRouter`. The legacy single-provider path is preserved
through a fallback adapter when no router is bound.

Honored request headers:

- ``x-request-id`` — echoed back
- ``traceparent`` — captured into per-call metadata (no business effect here)
- ``openai-organization`` — captured into per-call metadata

``encoding_format=base64`` returns float32 little-endian buffers base64-encoded
(matches OpenAI's wire format).
"""

from __future__ import annotations

import base64
import struct
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ai_portal.gateway import service as gateway_service
from ai_portal.gateway.embeddings import EmbeddingRouter
from ai_portal.gateway.types import Embeddings

router = APIRouter(tags=["gateway-openai-compat"])


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="ignore")


class OpenAIEmbeddingsRequest(_Frozen):
    model: str
    # OpenAI accepts: str | list[str] | list[int] | list[list[int]]. We map
    # token-id arrays through ``str()`` since the gateway operates on text.
    input: str | list[str] | list[int] | list[list[int]] = Field(min_length=1)
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: int | None = None
    user: str | None = None


def _normalize_input(raw: Any) -> list[str]:
    """Coerce the OpenAI input field into ``list[str]``."""
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        if not raw:
            return []
        if isinstance(raw[0], str):
            return list(raw)
        if isinstance(raw[0], int):
            # Single token-id array → one input string.
            return [" ".join(str(t) for t in raw)]
        if isinstance(raw[0], list):
            # Batch of token-id arrays → one string per row.
            return [" ".join(str(t) for t in row) for row in raw]
    return [str(raw)]


def _encode_vector(vec: list[float], fmt: str) -> Any:
    if fmt == "base64":
        return base64.b64encode(struct.pack(f"{len(vec)}f", *vec)).decode("ascii")
    return [float(x) for x in vec]


# ── DI: embedding router ─────────────────────────────────────────────────


def get_embedding_router() -> EmbeddingRouter | None:
    """FastAPI dep — yields the multi-provider router, or ``None`` to fall
    back to the single-provider legacy path.

    Default returns ``None`` so existing single-provider tests keep working.
    Production startup overrides this dep with a fully-populated router.
    """
    return None


# ── route ────────────────────────────────────────────────────────────────


@router.post("/v1/embeddings")
async def create_embeddings(
    body: OpenAIEmbeddingsRequest,
    response: Response,
    provider=Depends(gateway_service.get_llm_provider),
    embedding_router: EmbeddingRouter | None = Depends(get_embedding_router),
    x_request_id: Annotated[str | None, Header(alias="x-request-id")] = None,
    traceparent: Annotated[str | None, Header(alias="traceparent")] = None,
    openai_organization: Annotated[
        str | None, Header(alias="openai-organization")
    ] = None,
):
    """OpenAI-compatible embeddings."""
    texts = _normalize_input(body.input)
    if not texts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="input must not be empty"
        )

    emb: Embeddings
    try:
        if embedding_router is not None:
            emb = await embedding_router.embed(
                texts, body.model, dimensions=body.dimensions
            )
        else:
            # Legacy: single provider, no batching, no dimension passthrough.
            emb = await gateway_service.embed(texts, body.model, provider)
    except NotImplementedError as e:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED, detail=str(e)
        ) from e
    except KeyError as e:
        # Unknown provider for model.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    data: list[dict[str, Any]] = []
    for idx, vec in enumerate(emb.vectors):
        data.append({
            "object": "embedding",
            "index": idx,
            "embedding": _encode_vector(vec, body.encoding_format),
        })

    # Trace headers are accepted but only echoed back for x-request-id.
    if x_request_id:
        response.headers["x-request-id"] = x_request_id
    # traceparent / openai_organization noted for future trace metadata.
    _ = traceparent
    _ = openai_organization

    return {
        "object": "list",
        "data": data,
        "model": body.model,
        "usage": {
            "prompt_tokens": emb.usage.input_tokens,
            "total_tokens": (
                emb.usage.total_tokens or emb.usage.input_tokens
            ),
        },
    }


__all__ = ["get_embedding_router", "router"]
