from __future__ import annotations

import io
import json
import logging

import pandas as pd

from ai_portal.catalog.providers import get_chat_provider
from ai_portal.core.config import get_settings

logger = logging.getLogger(__name__)

_SAMPLE_ROWS = 20


def query_structured_data(data: str, question: str) -> str:
    """Parse CSV or JSON data and answer a question about it using the LLM."""
    df = _parse(data.strip())
    if df is None:
        return "Could not parse the provided data. Ensure it is valid CSV or JSON."

    schema = _describe(df)
    sample = df.head(_SAMPLE_ROWS).to_csv(index=False)

    system_prompt = (
        "You are a data analyst. The user has provided structured data. "
        "Answer the question accurately using only the data shown.\n\n"
        f"Schema:\n{schema}\n\n"
        f"Data sample (up to {_SAMPLE_ROWS} rows):\n{sample}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    try:
        chunks = list(get_chat_provider(get_settings()).stream_deltas(messages, model=None))
        return "".join(chunks)
    except Exception:
        logger.exception("data_query_llm_failed")
        return "Could not answer the question due to an internal error."


def _parse(data: str) -> pd.DataFrame | None:
    # Try JSON first
    try:
        parsed = json.loads(data)
        if isinstance(parsed, list):
            return pd.DataFrame(parsed)
        if isinstance(parsed, dict):
            return pd.DataFrame([parsed])
    except (json.JSONDecodeError, ValueError):
        pass

    # Try CSV
    try:
        df = pd.read_csv(io.StringIO(data))
        # Validate: must have at least 1 row of data
        if len(df) > 0:
            return df
    except Exception:
        pass

    return None


def _describe(df: pd.DataFrame) -> str:
    lines = [f"Columns ({len(df.columns)}): {', '.join(df.columns)}"]
    lines.append(f"Rows: {len(df)}")
    for col in df.columns:
        dtype = str(df[col].dtype)
        lines.append(f"  - {col} ({dtype})")
    return "\n".join(lines)
