from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import Integer, and_, case, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.chat.item_kinds import ItemKind
from ai_portal.chat.model import Thread, ThreadItem
from ai_portal.usage.consumption_schemas import (
    KpiCard, SummaryResponse, SummaryRow, ThreadRow, ThreadsResponse,
    TimelineItem, TimelineResponse, TrendPoint, TrendResponse,
)

ZERO = Decimal("0")


async def summary(*, session: AsyncSession, org_id: uuid.UUID,
                  start: datetime, end: datetime) -> SummaryResponse:
    kpis_row = (await session.execute(
        select(
            func.coalesce(func.sum(ThreadItem.cost_usd), 0),
            func.sum(case((ThreadItem.kind == ItemKind.llm_call, 1), else_=0)),
            func.sum(case((ThreadItem.kind == ItemKind.tool_call, 1), else_=0)),
        ).where(
            ThreadItem.org_id == org_id,
            ThreadItem.created_at >= start,
            ThreadItem.created_at <= end,
        )
    )).one()
    total_cost, llm_count, tool_count = kpis_row

    top_model = (await session.execute(
        select(ThreadItem.model, func.sum(ThreadItem.cost_usd).label("s"))
        .where(
            ThreadItem.org_id == org_id,
            ThreadItem.kind == ItemKind.llm_call,
            ThreadItem.created_at >= start, ThreadItem.created_at <= end,
        )
        .group_by(ThreadItem.model)
        .order_by(func.sum(ThreadItem.cost_usd).desc())
        .limit(1)
    )).first()

    kpis = [
        KpiCard(label="Month spend", value=Decimal(str(total_cost or 0)), unit="USD"),
        KpiCard(label="Messages streamed", value=int(llm_count or 0)),
        KpiCard(label="Tool calls", value=int(tool_count or 0)),
        KpiCard(
            label="Top model",
            value=(top_model[0] if top_model else "—") or "—",
            unit=(str(Decimal(str(top_model[1] or 0))) if top_model else None),
        ),
    ]

    by_model = await _group(session, org_id, start, end, ThreadItem.model)
    by_user = await _group_via_thread(session, org_id, start, end)
    by_provider = await _group(session, org_id, start, end, ThreadItem.provider)
    cap_stmt = (
        select(
            func.jsonb_array_elements_text(ThreadItem.data["capabilities"]).label("capability"),
            func.count(ThreadItem.id).label("messages"),
            func.coalesce(func.sum(cast(ThreadItem.data["input_tokens"].astext, Integer)), 0).label("input_tokens"),
            func.coalesce(func.sum(cast(ThreadItem.data["output_tokens"].astext, Integer)), 0).label("output_tokens"),
            func.coalesce(func.sum(ThreadItem.cost_usd), 0).label("cost_usd"),
            func.avg(case((ThreadItem.cost_estimated.is_(True), 1.0), else_=0.0)).label("estimated_ratio"),
        )
        .where(
            ThreadItem.org_id == org_id,
            ThreadItem.kind == ItemKind.llm_call,
            ThreadItem.created_at >= start,
            ThreadItem.created_at <= end,
            ThreadItem.data["capabilities"].isnot(None),
        )
        .group_by(text("1"))
        .order_by(func.sum(ThreadItem.cost_usd).desc().nullslast())
    )
    cap_rows = (await session.execute(cap_stmt)).all()
    by_capability = [
        SummaryRow(
            key=r.capability, label=r.capability,
            messages=int(r.messages),
            input_tokens=int(r.input_tokens or 0),
            output_tokens=int(r.output_tokens or 0),
            cost_usd=Decimal(str(r.cost_usd or 0)),
            estimated_ratio=float(r.estimated_ratio or 0.0),
        )
        for r in cap_rows
        if r.capability
    ]
    by_tool = await _group(
        session, org_id, start, end,
        func.coalesce(ThreadItem.data["tool_name"].astext, "?"),
        only_kind=ItemKind.tool_call,
    )

    return SummaryResponse(
        kpis=kpis, by_model=by_model, by_user=by_user, by_provider=by_provider,
        by_capability=by_capability, by_tool=by_tool,
    )


async def _group(session, org_id, start, end, column, *, only_kind=None) -> list[SummaryRow]:
    where = [
        ThreadItem.org_id == org_id,
        ThreadItem.created_at >= start, ThreadItem.created_at <= end,
    ]
    if only_kind is not None:
        where.append(ThreadItem.kind == only_kind)
    stmt = (
        select(
            column.label("k"),
            func.count(ThreadItem.id),
            func.coalesce(func.sum(cast(ThreadItem.data["input_tokens"].astext, Integer)), 0),
            func.coalesce(func.sum(cast(ThreadItem.data["output_tokens"].astext, Integer)), 0),
            func.coalesce(func.sum(ThreadItem.cost_usd), 0),
            func.avg(case((ThreadItem.cost_estimated.is_(True), 1.0), else_=0.0)),
        )
        .where(and_(*where))
        .group_by(column)
        .order_by(func.sum(ThreadItem.cost_usd).desc().nullslast())
        .limit(50)
    )
    rows = (await session.execute(stmt)).all()
    out: list[SummaryRow] = []
    for k, msgs, it, ot, cost, est in rows:
        key = str(k) if k is not None else "(none)"
        out.append(SummaryRow(
            key=key, label=key, messages=int(msgs),
            input_tokens=int(it or 0), output_tokens=int(ot or 0),
            cost_usd=Decimal(str(cost or 0)), estimated_ratio=float(est or 0.0),
        ))
    return out


async def _group_via_thread(session, org_id, start, end) -> list[SummaryRow]:
    stmt = (
        select(
            Thread.user_id.label("k"),
            func.count(ThreadItem.id),
            func.coalesce(func.sum(cast(ThreadItem.data["input_tokens"].astext, Integer)), 0),
            func.coalesce(func.sum(cast(ThreadItem.data["output_tokens"].astext, Integer)), 0),
            func.coalesce(func.sum(ThreadItem.cost_usd), 0),
            func.avg(case((ThreadItem.cost_estimated.is_(True), 1.0), else_=0.0)),
        )
        .join(Thread, Thread.id == ThreadItem.thread_id)
        .where(ThreadItem.org_id == org_id, ThreadItem.created_at >= start, ThreadItem.created_at <= end)
        .group_by(Thread.user_id)
        .order_by(func.sum(ThreadItem.cost_usd).desc().nullslast())
        .limit(50)
    )
    rows = (await session.execute(stmt)).all()
    return [SummaryRow(
        key=str(k), label=str(k), messages=int(m),
        input_tokens=int(it or 0), output_tokens=int(ot or 0),
        cost_usd=Decimal(str(c or 0)), estimated_ratio=float(e or 0.0),
    ) for k, m, it, ot, c, e in rows]


async def trend(*, session: AsyncSession, org_id: uuid.UUID,
                start: datetime, end: datetime,
                grain: Literal["day", "hour"], by: Literal["kind", "provider"]) -> TrendResponse:
    trunc = func.date_trunc(grain, ThreadItem.created_at)
    key_col = ThreadItem.kind if by == "kind" else ThreadItem.provider
    stmt = (
        select(
            trunc.label("t"), key_col.label("k"),
            func.coalesce(func.sum(ThreadItem.cost_usd), 0),
            func.coalesce(func.sum(cast(ThreadItem.data["input_tokens"].astext, Integer)), 0),
            func.coalesce(func.sum(cast(ThreadItem.data["output_tokens"].astext, Integer)), 0),
        )
        .where(ThreadItem.org_id == org_id, ThreadItem.created_at >= start, ThreadItem.created_at <= end)
        .group_by(trunc, key_col)
        .order_by(trunc)
    )
    rows = (await session.execute(stmt)).all()
    buckets: dict = {}
    for t, k, cost, it, ot in rows:
        b = buckets.setdefault(t, {"cost_usd": ZERO, "in": 0, "out": 0, "by": {}})
        b["cost_usd"] += Decimal(str(cost or 0))
        b["in"] += int(it or 0)
        b["out"] += int(ot or 0)
        kk = (k.value if hasattr(k, "value") else (k or "other"))
        b["by"][kk] = b["by"].get(kk, ZERO) + Decimal(str(cost or 0))
    series = [TrendPoint(t=t, cost_usd=v["cost_usd"], input_tokens=v["in"], output_tokens=v["out"], breakdown=v["by"])
              for t, v in sorted(buckets.items())]
    return TrendResponse(grain=grain, by=by, series=series)


async def threads(*, session: AsyncSession, org_id: uuid.UUID,
                  start: datetime, end: datetime, user_id: int | None, model: str | None,
                  page: int, page_size: int) -> ThreadsResponse:
    where = [Thread.org_id == org_id, Thread.last_message_at >= start, Thread.last_message_at <= end]
    if user_id is not None:
        where.append(Thread.user_id == user_id)
    if model is not None:
        where.append(Thread.model == model)

    total = (await session.execute(select(func.count(Thread.id)).where(and_(*where)))).scalar_one()
    stmt = (
        select(Thread.id, Thread.title, Thread.user_id, Thread.model, Thread.last_message_at,
               func.coalesce(func.sum(ThreadItem.cost_usd), 0).label("cost"),
               func.count(ThreadItem.id).label("items"))
        .outerjoin(ThreadItem, ThreadItem.thread_id == Thread.id)
        .where(and_(*where))
        .group_by(Thread.id)
        .order_by(Thread.last_message_at.desc().nullslast())
        .offset((page - 1) * page_size).limit(page_size)
    )
    rows = (await session.execute(stmt)).all()
    return ThreadsResponse(
        total=int(total), page=page, page_size=page_size,
        rows=[ThreadRow(id=r[0], title=r[1], user_id=r[2], model=r[3], last_message_at=r[4],
                        total_cost_usd=Decimal(str(r[5] or 0)), total_items=int(r[6] or 0))
              for r in rows],
    )


async def timeline(*, session: AsyncSession, org_id: uuid.UUID, thread_id: int) -> TimelineResponse:
    stmt = (select(ThreadItem)
            .where(ThreadItem.thread_id == thread_id, ThreadItem.org_id == org_id)
            .order_by(ThreadItem.created_at, ThreadItem.id))
    rows = (await session.execute(stmt)).scalars().all()
    return TimelineResponse(thread_id=thread_id, items=[TimelineItem.model_validate(r) for r in rows])
