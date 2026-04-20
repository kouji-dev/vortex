from __future__ import annotations


def compose(*, base_prompt: str, assistant_prompt: str | None, memory_block: str | None,
            kb_block: str | None, capabilities: list[str]) -> str:
    parts: list[str] = [base_prompt.strip()]
    if assistant_prompt and assistant_prompt.strip():
        parts.append(assistant_prompt.strip())
    if memory_block and memory_block.strip():
        parts.append("## Memory\n" + memory_block.strip())
    if kb_block and kb_block.strip():
        parts.append("## Knowledge base\n" + kb_block.strip())
    if capabilities:
        parts.append("## Available tools\n- " + "\n- ".join(capabilities))
    return "\n\n".join(p for p in parts if p)
