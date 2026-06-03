from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from .conversation import Conversation
from .tool_registry import Tool


@dataclass
class AgentConfig:
    model: str = "claude-sonnet-4-6"
    system_prompt: str = "Du bist ein hilfreicher Assistent."
    max_turns: int = 25
    max_tokens: int = 4096
    temperature: float = 0.0
    max_result_length: int = 50000


def run_agent(
    config: AgentConfig,
    tools: list[Tool],
    user_message: str,
    conversation: Optional[Conversation] = None,
    verbose: bool = False,
) -> str:
    """Run an agent loop: send message, handle tool calls, repeat until text response."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if conversation is None:
        conversation = Conversation()

    tool_map = {t.name: t for t in tools}
    conversation.add_user(user_message)

    for turn in range(config.max_turns):
        if verbose:
            print(f"  [turn {turn + 1}]")

        api_kwargs = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "system": config.system_prompt,
            "messages": conversation.get_messages(),
        }
        if config.temperature > 0:
            api_kwargs["temperature"] = config.temperature
        if tools:
            api_kwargs["tools"] = [t.to_anthropic_schema() for t in tools]

        response = client.messages.create(**api_kwargs)

        # Extract text from response
        text_parts = [b.text for b in response.content if b.type == "text"]

        if response.stop_reason == "end_turn":
            conversation.add_assistant(response.content)
            return "\n".join(text_parts) if text_parts else ""

        if response.stop_reason == "tool_use":
            # Store full assistant response (API requires echoing it back)
            conversation.add_assistant(response.content)

            # Execute all tool calls
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool = tool_map.get(block.name)
                if tool is None:
                    result_str = f"Error: Unknown tool '{block.name}'"
                else:
                    try:
                        result = tool.execute(**block.input)
                        if isinstance(result, (dict, list)):
                            result_str = json.dumps(result, ensure_ascii=False)
                        else:
                            result_str = str(result)
                    except Exception as e:
                        result_str = f"Error executing {block.name}: {e}"

                # Truncate large results
                if len(result_str) > config.max_result_length:
                    result_str = result_str[:config.max_result_length] + "\n... (truncated)"

                if verbose:
                    print(f"  [{block.name}] -> {result_str[:200]}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

            conversation.add_tool_results(tool_results)
            continue

        # max_tokens or other stop reason
        conversation.add_assistant(response.content)
        return "\n".join(text_parts) if text_parts else ""

    return "Agent hat max_turns erreicht ohne abzuschliessen."
