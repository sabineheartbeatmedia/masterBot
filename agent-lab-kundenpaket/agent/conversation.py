from __future__ import annotations

from typing import Any


def _serialize_content(content: Any) -> Any:
    """Convert Anthropic SDK content blocks to plain dicts for safe storage."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        result = []
        for block in content:
            if hasattr(block, "type"):
                # Anthropic SDK ContentBlock object
                if block.type == "text":
                    result.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    result.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                elif block.type == "tool_result":
                    result.append({
                        "type": "tool_result",
                        "tool_use_id": block.get("tool_use_id", ""),
                        "content": block.get("content", ""),
                    })
                else:
                    # Unknown block type, try to convert
                    if hasattr(block, "model_dump"):
                        result.append(block.model_dump())
                    else:
                        result.append({"type": block.type})
            elif isinstance(block, dict):
                result.append(block)
        return result
    # Fallback: try model_dump for single objects
    if hasattr(content, "model_dump"):
        return content.model_dump()
    return content


class Conversation:
    """In-memory conversation history for session persistence."""

    def __init__(self):
        self.messages: list[dict] = []

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: Any):
        self.messages.append({"role": "assistant", "content": _serialize_content(content)})

    def add_tool_results(self, tool_results: list[dict]):
        self.messages.append({"role": "user", "content": tool_results})

    def get_messages(self) -> list[dict]:
        return list(self.messages)
