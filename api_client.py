import asyncio
import json
import logging
from typing import Optional, Tuple, List, Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

import config
import web_search

logger = logging.getLogger("overlay_assistant.api_client")


class WebSearchArgs(BaseModel):
    """Pydantic model defining arguments for the web_search tool."""
    query: str = Field(description="The search query to execute.")


def _build_web_search_tool() -> dict:
    """
    Constructs the OpenAI tool declaration dict using Pydantic.
    Strips 'title' attributes to ensure compatibility with local GGUF model templates.
    """
    schema = WebSearchArgs.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        if isinstance(prop, dict):
            prop.pop("title", None)

    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web for up-to-date information, news, current events, or real-time data.",
            "parameters": schema
        }
    }


WEB_SEARCH_TOOL = _build_web_search_tool()


class Conversation:
    """Holds messages[] for one hotkey session. Discarded on next trigger."""

    def __init__(self, full_b64: str, crop_b64: str):
        self.messages = [
            {"role": "system", "content": config.SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Full screenshot for context:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{full_b64}"}},
                    {"type": "text", "text": "Highlighted region (focus on this):"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{crop_b64}"}},
                ],
            },
        ]

    def add_user_text(self, text: str):
        self.messages.append({"role": "user", "content": text})

    def add_assistant_text(self, text: str):
        self.messages.append({"role": "assistant", "content": text})

    def add_tool_result(self, tool_call_id: str, name: str, result: str):
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result
        })


async def _stream_request(
    messages: List[dict],
    tools: Optional[List[dict]] = None,
    on_token=None
) -> Tuple[str, List[dict], Optional[str]]:
    """
    Sends a streaming POST request to llama.cpp server via AsyncOpenAI client SDK,
    accumulates text content or tool call deltas, and returns the aggregated response.
    """
    # Normalize base_url for AsyncOpenAI client
    base_url = config.LLAMA_SERVER_URL
    if base_url.endswith("/chat/completions"):
        base_url = base_url[:-len("/chat/completions")]

    client = AsyncOpenAI(base_url=base_url, api_key="llama.cpp")

    kwargs: dict[str, Any] = {
        "model": config.MODEL_NAME,
        "messages": messages,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools

    full_text = ""
    tool_calls_acc: dict[int, dict] = {}
    finish_reason = None

    try:
        response_stream = await client.chat.completions.create(**kwargs)
        async for chunk in response_stream:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason

            delta = choice.delta
            if not delta:
                continue

            # Standard text content
            if delta.content:
                full_text += delta.content
                if on_token:
                    on_token(delta.content)

            # Accumulate streaming tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc.id or f"call_{idx}",
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        }
                    if tc.id:
                        tool_calls_acc[idx]["id"] = tc.id

                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]["function"]["arguments"] += tc.function.arguments

    except Exception:
        logger.exception("_stream_request: Failed during OpenAI streaming completion")
        raise
    finally:
        await client.close()

    assembled_tool_calls = [v for k, v in sorted(tool_calls_acc.items())]
    return full_text, assembled_tool_calls, finish_reason


async def stream_reply_with_tools(conversation: Conversation, on_token, status_callback=None) -> str:
    """
    Handles streaming responses with an agentic tool-calling loop.
    Supports multi-turn tool calling compatible with local GGUF model templates.
    """
    iterations = 0

    while iterations < config.MAX_TOOL_ITERATIONS:
        iterations += 1
        logger.info("stream_reply_with_tools: model turn %s/%s", iterations, config.MAX_TOOL_ITERATIONS)

        full_text, tool_calls, finish_reason = await _stream_request(
            conversation.messages,
            tools=[WEB_SEARCH_TOOL],
            on_token=on_token,
        )

        # Model produced final answer (no tool calls requested)
        if not tool_calls and finish_reason != "tool_calls":
            conversation.add_assistant_text(full_text)
            if status_callback:
                status_callback("")  # Clear status line
            logger.info("stream_reply_with_tools: final answer received after %s iteration(s)", iterations)
            return full_text

        # Record assistant tool_calls message
        assistant_msg = {
            "role": "assistant",
            "content": full_text if full_text else None,
            "tool_calls": tool_calls
        }
        conversation.messages.append(assistant_msg)

        # Execute each requested tool call
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            call_id = tc["id"]

            if fn_name == "web_search":
                try:
                    args = json.loads(raw_args)
                    query = args.get("query", "")
                except json.JSONDecodeError:
                    query = raw_args.strip()

                if not query or not query.strip():
                    logger.warning("stream_reply_with_tools: empty web_search query from model, skipping")
                    conversation.add_tool_result(
                        call_id,
                        fn_name,
                        "Error: The web_search query was empty. Please provide a specific, non-empty search query.",
                    )
                    continue

                if status_callback:
                    status_callback(f"🔍 Searching: {query}...")

                search_result = await web_search.search(query)
                conversation.add_tool_result(call_id, fn_name, search_result)
            else:
                conversation.add_tool_result(
                    call_id,
                    fn_name,
                    f"Error: Unrecognized tool '{fn_name}'.",
                )

        if status_callback:
            status_callback("")

    # Iteration cap reached — force final answer without tools
    logger.warning("stream_reply_with_tools: reached MAX_TOOL_ITERATIONS=%s, forcing final answer", config.MAX_TOOL_ITERATIONS)
    final_text, _, _ = await _stream_request(
        conversation.messages,
        tools=None,
        on_token=on_token,
    )
    conversation.add_assistant_text(final_text)
    return final_text


async def stream_reply(conversation: Conversation, on_token, status_callback=None) -> str:
    """
    Entry point for generating replies. Delegates to tool loop if WEB_SEARCH_ENABLED.
    """
    if config.WEB_SEARCH_ENABLED:
        return await stream_reply_with_tools(conversation, on_token, status_callback)

    full_text, _, _ = await _stream_request(
        conversation.messages,
        tools=None,
        on_token=on_token,
    )
    conversation.add_assistant_text(full_text)
    return full_text