"""OpenAI-compatible Chat Completions surface — ``POST /v1/chat/completions``.

Translation layer:

- OpenAI ``ChatCompletionRequest`` shape → :class:`LLMRequest`
- :class:`LLMResponse` → OpenAI ``chat.completion`` object
- :class:`StreamChunk` stream → SSE ``data: {chat.completion.chunk}\\n\\n``
  frames terminated by ``data: [DONE]``

Honored request headers:

- ``x-request-id`` — echoed back on the response
- ``traceparent`` — captured into ``LLMRequest.metadata`` for downstream
  propagation (OTEL link)
- ``openai-organization`` — captured into ``LLMRequest.metadata``
- ``Authorization: Bearer ...`` — handled upstream by the auth middleware

No business logic lives here. Cache / guardrails / routing all happen inside
:func:`gateway.service.complete` and :func:`gateway.service.stream`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ai_portal.gateway import service as gateway_service
from ai_portal.gateway.policies import (
    BudgetExceeded,
    complete_with_policies,
)

logger = logging.getLogger(__name__)
from ai_portal.gateway.types import (
    LLMRequest,
    LLMResponse,
    Message,
    StreamChunk,
    TextBlock,
    ToolDef,
)

router = APIRouter(tags=["gateway-openai-compat"])


# ── OpenAI request schemas ───────────────────────────────────────────────


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="ignore")


class OpenAITextContentPart(_Frozen):
    type: Literal["text"]
    text: str


class OpenAIImageURL(_Frozen):
    url: str
    detail: str | None = None


class OpenAIImageContentPart(_Frozen):
    type: Literal["image_url"]
    image_url: OpenAIImageURL


OpenAIContentPart = Annotated[
    OpenAITextContentPart | OpenAIImageContentPart, Field(discriminator="type")
]


class OpenAIChatMessage(_Frozen):
    role: Literal["system", "user", "assistant", "tool", "developer"]
    content: str | list[OpenAIContentPart] | None = None
    name: str | None = None
    tool_call_id: str | None = None


class OpenAIFunctionTool(_Frozen):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class OpenAITool(_Frozen):
    type: Literal["function"]
    function: OpenAIFunctionTool


class OpenAIStreamOptions(_Frozen):
    include_usage: bool = False


class OpenAIResponseFormat(_Frozen):
    # raw pass-through; full json_schema mapping lands later.
    type: Literal["text", "json_object", "json_schema"] = "text"
    json_schema: dict[str, Any] | None = None


class OpenAIChatCompletionsRequest(_Frozen):
    model: str
    messages: list[OpenAIChatMessage] = Field(min_length=1)
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: str | list[str] | None = None
    stream: bool = False
    stream_options: OpenAIStreamOptions | None = None
    tools: list[OpenAITool] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: OpenAIResponseFormat | None = None
    user: str | None = None
    n: int | None = None


# ── OpenAI response schemas ──────────────────────────────────────────────


# Loose dicts — the OpenAI shape is wide and pydantic-validating the *response*
# costs more than it pays. We hand-build dicts and return them via JSONResponse.


# ── translation: OpenAI → canonical LLMRequest ───────────────────────────


_STOP_TO_OPENAI: dict[str, str] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "content_filter": "content_filter",
    "unknown": "stop",
}


def _content_to_blocks(content: str | list[OpenAIContentPart] | None) -> list:
    """Translate an OpenAI message ``content`` field into canonical blocks."""
    if content is None or content == "":
        return [TextBlock(text="")]
    if isinstance(content, str):
        return [TextBlock(text=content)]
    blocks: list = []
    for part in content:
        if isinstance(part, OpenAITextContentPart):
            blocks.append(TextBlock(text=part.text))
        elif isinstance(part, OpenAIImageContentPart):
            from ai_portal.gateway.types import ImageBlock
            blocks.append(ImageBlock(url=part.image_url.url))
    if not blocks:
        blocks.append(TextBlock(text=""))
    return blocks


def _role_to_canonical(role: str) -> Literal["system", "user", "assistant", "tool"]:
    # OpenAI's "developer" role (o1+) maps to "system" canonically.
    if role == "developer":
        return "system"
    if role in ("system", "user", "assistant", "tool"):
        return role  # type: ignore[return-value]
    return "user"


def request_to_canonical(
    body: OpenAIChatCompletionsRequest,
    *,
    traceparent: str | None,
    organization: str | None,
) -> LLMRequest:
    """OpenAI request → canonical :class:`LLMRequest`."""
    messages: list[Message] = []
    for m in body.messages:
        messages.append(
            Message(
                role=_role_to_canonical(m.role),
                content=_content_to_blocks(m.content),
                name=m.name,
            )
        )

    tools: list[ToolDef] | None = None
    if body.tools:
        tools = [
            ToolDef(
                name=t.function.name,
                description=t.function.description,
                input_schema=t.function.parameters,
            )
            for t in body.tools
        ]

    stop: list[str] | None = None
    if isinstance(body.stop, str):
        stop = [body.stop]
    elif isinstance(body.stop, list):
        stop = body.stop

    metadata: dict[str, Any] = {}
    if traceparent:
        metadata["traceparent"] = traceparent
    if organization:
        metadata["openai_organization"] = organization
    if body.stream_options is not None:
        metadata["openai_stream_options"] = body.stream_options.model_dump()
    if body.response_format is not None:
        metadata["openai_response_format"] = body.response_format.model_dump()

    return LLMRequest(
        model=body.model,
        messages=messages,
        tools=tools,
        stream=body.stream,
        max_tokens=body.max_tokens or body.max_completion_tokens,
        temperature=body.temperature,
        top_p=body.top_p,
        stop=stop,
        metadata=metadata,
        user=body.user,
    )


# ── translation: canonical LLMResponse → OpenAI ──────────────────────────


def _content_text(resp: LLMResponse) -> str:
    out: list[str] = []
    for block in resp.content:
        # block is a discriminated union instance from the canonical types.
        if isinstance(block, TextBlock):
            out.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            out.append(str(block.get("text", "")))
    return "".join(out)


def _openai_id(prefix: str = "chatcmpl") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:24]}"


def response_to_openai(resp: LLMResponse, *, model: str) -> dict[str, Any]:
    """Canonical :class:`LLMResponse` → OpenAI ``chat.completion`` dict."""
    text = _content_text(resp)
    tool_calls_out: list[dict[str, Any]] = []
    for tc in resp.tool_calls:
        tool_calls_out.append({
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.name,
                "arguments": json.dumps(tc.arguments),
            },
        })

    message: dict[str, Any] = {
        "role": "assistant",
        "content": text if text else None,
    }
    if tool_calls_out:
        message["tool_calls"] = tool_calls_out

    finish = _STOP_TO_OPENAI.get(resp.stop_reason, "stop")

    return {
        "id": _openai_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish,
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": resp.usage.input_tokens,
            "completion_tokens": resp.usage.output_tokens,
            "total_tokens": (
                resp.usage.total_tokens
                or resp.usage.input_tokens + resp.usage.output_tokens
            ),
        },
    }


# ── streaming: canonical chunks → OpenAI SSE frames ──────────────────────


async def _sse_stream(
    chunks: AsyncIterator[StreamChunk],
    *,
    model: str,
    include_usage: bool,
) -> AsyncIterator[bytes]:
    """Yield OpenAI-shaped SSE frames terminated by ``data: [DONE]``."""
    chat_id = _openai_id()
    created = int(time.time())

    def _frame(delta: dict[str, Any], *, finish_reason: str | None = None,
               usage: dict[str, Any] | None = None) -> bytes:
        payload: dict[str, Any] = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                    "logprobs": None,
                }
            ],
        }
        if usage is not None:
            payload["usage"] = usage
        return f"data: {json.dumps(payload)}\n\n".encode()

    # First frame announces the assistant role (OpenAI convention).
    yield _frame({"role": "assistant", "content": ""})

    finish_reason: str | None = None
    last_usage: dict[str, Any] | None = None

    async for chunk in chunks:
        root = chunk.root
        t = root.type
        if t == "text_delta":
            yield _frame({"content": root.text})
        elif t == "tool_call_request":
            yield _frame({
                "tool_calls": [
                    {
                        "index": 0,
                        "id": root.call_id,
                        "type": "function",
                        "function": {
                            "name": root.tool_name,
                            "arguments": json.dumps(root.arguments),
                        },
                    }
                ]
            })
        elif t == "usage":
            last_usage = {
                "prompt_tokens": root.input_tokens,
                "completion_tokens": root.output_tokens,
                "total_tokens": root.input_tokens + root.output_tokens,
            }
        elif t == "iteration_complete":
            finish_reason = _STOP_TO_OPENAI.get(root.stop_reason, "stop")
        elif t == "provider_error":
            # Surface as a terminal frame with finish_reason=stop + an error
            # marker on the delta. SDKs typically swallow this — admins should
            # consult traces for the real error.
            yield _frame({"content": f"[provider_error:{root.code}]"})
            finish_reason = "stop"

    # Final delta frame with finish_reason set.
    final_usage = last_usage if include_usage else None
    yield _frame({}, finish_reason=finish_reason or "stop", usage=final_usage)
    yield b"data: [DONE]\n\n"


# ── route ────────────────────────────────────────────────────────────────


def _emit_observability(
    *,
    req: LLMRequest,
    response_obj: LLMResponse | None,
    provider_name: str,
    request_obj: Request,
    started_at: float,
    status_str: str,
    error: str | None,
    cost_cents: float,
) -> None:
    """Best-effort: fire trace + audit + usage through the default facade.

    Skips cleanly when no default facade is installed or no actor is found
    (unauthenticated calls during smoke tests still go through but skip
    observability). Never raises into the request path.
    """
    try:
        from ai_portal.gateway.facade import Actor, get_default_facade  # noqa: PLC0415

        try:
            facade = get_default_facade()
        except RuntimeError:
            return  # no facade installed — silently skip

        user = getattr(request_obj.state, "current_user", None)
        if user is None or getattr(user, "org_id", None) is None:
            return  # no actor to attribute the call to

        actor = Actor(
            org_id=user.org_id,
            user_id=getattr(user, "id", None),
            kind="user",
        )
        latency_ms = int((time.monotonic() - started_at) * 1000)
        from ai_portal.gateway.types import Usage  # noqa: PLC0415
        usage = response_obj.usage if response_obj is not None else Usage()
        facade.record_call(
            actor=actor,
            req=req,
            model_used=(response_obj.model_used if response_obj else req.model),
            provider_name=provider_name,
            status=status_str,
            latency_ms=latency_ms,
            usage=usage,
            cost_cents=cost_cents,
            error=error,
            event_type="gateway.completion",
        )
    except Exception:  # noqa: BLE001
        logger.exception("openai_compat: observability emit failed")


def _try_resolve_actor_user(request_obj: Request) -> Any | None:
    """Best-effort: resolve the dev/Entra user without making auth mandatory.

    Returns ``None`` for unauthenticated requests so legacy tests + the
    existing public surface keep working. Production deployments layer real
    auth on top (gateway in front, or future API-key dep).
    """
    try:
        from ai_portal.auth.deps import _authenticate  # noqa: PLC0415
        from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None

    authz = request_obj.headers.get("authorization")
    if not authz:
        return None
    try:
        with SessionLocal() as db:
            return _authenticate(request_obj, authz, db)
    except Exception:  # noqa: BLE001
        return None


@router.post("/v1/chat/completions")
async def create_chat_completion(
    body: OpenAIChatCompletionsRequest,
    response: Response,
    request: Request,
    provider=Depends(gateway_service.get_llm_provider),
    policy_ctx: gateway_service.PolicyContext = Depends(
        gateway_service.get_policy_context
    ),
    x_request_id: Annotated[str | None, Header(alias="x-request-id")] = None,
    traceparent: Annotated[str | None, Header(alias="traceparent")] = None,
    openai_organization: Annotated[
        str | None, Header(alias="openai-organization")
    ] = None,
):
    """OpenAI-compatible chat completions.

    Honors ``stream=true`` via SSE; otherwise returns a single JSON response.
    Applies the active :class:`PolicyContext`: cost calculation (cost
    header), budget cutoff (402), prompt cache (cache_hit header).
    """
    req = request_to_canonical(
        body, traceparent=traceparent, organization=openai_organization
    )
    request.state.current_user = _try_resolve_actor_user(request)
    started_at = time.monotonic()
    provider_name = getattr(provider, "name", "unknown")

    if body.stream:
        include_usage = bool(
            body.stream_options and body.stream_options.include_usage
        )
        agen = gateway_service.stream(req, provider)
        headers: dict[str, str] = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
        if x_request_id:
            headers["x-request-id"] = x_request_id
        return StreamingResponse(
            _sse_stream(agen, model=body.model, include_usage=include_usage),
            media_type="text/event-stream",
            headers=headers,
        )

    try:
        result = await complete_with_policies(
            req,
            provider,
            pricing=policy_ctx.pricing,
            cache=policy_ctx.cache,
            cache_ttl_seconds=policy_ctx.cache_ttl_seconds,
            budget_check=policy_ctx.budget_check,  # type: ignore[arg-type]
            estimated_cost_usd=policy_ctx.estimated_cost_usd,
            on_cache_hit_usage=policy_ctx.on_cache_hit_usage,  # type: ignore[arg-type]
        )
    except BudgetExceeded as e:
        _emit_observability(
            req=req, response_obj=None, provider_name=provider_name,
            request_obj=request, started_at=started_at, status_str="error",
            error=f"budget_exceeded:{e.reason}", cost_cents=0.0,
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=e.reason,
            headers=e.headers,
        ) from e
    except NotImplementedError as e:
        _emit_observability(
            req=req, response_obj=None, provider_name=provider_name,
            request_obj=request, started_at=started_at, status_str="error",
            error=str(e), cost_cents=0.0,
        )
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED, detail=str(e)
        ) from e
    except Exception as e:  # noqa: BLE001
        _emit_observability(
            req=req, response_obj=None, provider_name=provider_name,
            request_obj=request, started_at=started_at, status_str="error",
            error=str(e), cost_cents=0.0,
        )
        raise

    if x_request_id:
        response.headers["x-request-id"] = x_request_id
    for k, v in result.headers.items():
        response.headers[k] = v
    _emit_observability(
        req=req, response_obj=result.response, provider_name=provider_name,
        request_obj=request, started_at=started_at, status_str="ok",
        error=None, cost_cents=result.cost_cents,
    )
    return response_to_openai(result.response, model=body.model)


__all__ = [
    "request_to_canonical",
    "response_to_openai",
    "router",
]
