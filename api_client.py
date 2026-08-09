import asyncio
import json
import logging

import httpx
from httpx_sse import aconnect_sse

import config
import web_search

logger = logging.getLogger("overlay_assistant.api_client")

# Define OpenAI-compatible web search tool declaration
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Searches the web for up-to-date information, news, current events, or real-time data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to execute."
                }
            },
            "required": ["query"]
        }
    }
}


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


async def _stream_request(payload: dict, on_token):
    """
    Helper function to send streaming POST request to llama.cpp server,
    accumulate content or tool call deltas, and return final completion status.
    """
    full_text = ""
    tool_calls_acc = {}
    finish_reason = None

    async with httpx.AsyncClient(timeout=None) as client:
        async with aconnect_sse(client, "POST", config.LLAMA_SERVER_URL, json=payload) as event_source:
            logger.info("_stream_request: http status=%s", event_source.response.status_code)
            event_source.response.raise_for_status()

            async for event in event_source.aiter_sse():
                if event.data == "[DONE]":
                    logger.info("_stream_request: received [DONE]")
                    continue

                try:
                    chunk = json.loads(event.data)
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    
                    if choice.get("finish_reason"):
                        finish_reason = choice.get("finish_reason")

                    # Handle standard text content
                    content = delta.get("content", "")
                    if content:
                        full_text += content
                        if on_token:
                            on_token(content)

                    # Accumulate tool calls deltas
                    tool_calls_delta = delta.get("tool_calls", [])
                    for tc in tool_calls_delta:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc.get("id", f"call_{idx}"),
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        if tc.get("id"):
                            tool_calls_acc[idx]["id"] = tc["id"]
                        
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_calls_acc[idx]["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            tool_calls_acc[idx]["function"]["arguments"] += fn["arguments"]

                except Exception:
                    logger.exception("_stream_request: failed parsing stream chunk: %r", event.data[:300])
                    continue

    assembled_tool_calls = [v for k, v in sorted(tool_calls_acc.items())]
    return full_text, assembled_tool_calls, finish_reason


async def stream_reply_with_tools(conversation: Conversation, on_token, status_callback=None):
    """
    Handles streaming responses with a true agentic tool-calling loop.

    The model may perform multiple consecutive web searches autonomously.
    Each iteration sends the full conversation WITH tools declared, executes
    any requested tool calls, appends results, and loops again until the model
    produces a final answer (no tool calls) or the iteration cap is reached.
    """
    payload = {
        "model": config.MODEL_NAME,
        "messages": conversation.messages,
        "stream": True,
        "tools": [WEB_SEARCH_TOOL]
    }

    iterations = 0

    while iterations < config.MAX_TOOL_ITERATIONS:
        iterations += 1
        logger.info("stream_reply_with_tools: model turn %s/%s", iterations, config.MAX_TOOL_ITERATIONS)

        full_text, tool_calls, finish_reason = await _stream_request(payload, on_token)

        # Model produced the final answer (no tool calls requested)
        if not tool_calls and finish_reason != "tool_calls":
            conversation.add_assistant_text(full_text)
            if status_callback:
                status_callback("")  # Clear status line
            logger.info("stream_reply_with_tools: final answer received after %s iteration(s)", iterations)
            return full_text

        # Model requested tool calls — record the assistant tool_calls message
        assistant_msg = {"role": "assistant", "tool_calls": tool_calls}
        if full_text:
            assistant_msg["content"] = full_text
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

                # Guard against empty/malformed queries: return a helpful
                # tool result so the model can retry with a proper query
                # instead of hitting the search API with an empty string.
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

        # Clear status line before next model turn
        if status_callback:
            status_callback("")

    # Iteration cap reached — force a final answer without tools to avoid
    # an infinite loop and to stay within the context window.
    logger.warning("stream_reply_with_tools: reached MAX_TOOL_ITERATIONS=%s, forcing final answer", config.MAX_TOOL_ITERATIONS)
    force_payload = {
        "model": config.MODEL_NAME,
        "messages": conversation.messages,
        "stream": True,
    }
    final_text, _, _ = await _stream_request(force_payload, on_token)
    conversation.add_assistant_text(final_text)
    return final_text


async def stream_reply(conversation: Conversation, on_token, status_callback=None):
    """
    Entry point for generating replies. Delegates to tool loop if WEB_SEARCH_ENABLED.
    """
    if config.WEB_SEARCH_ENABLED:
        return await stream_reply_with_tools(conversation, on_token, status_callback)

    # Fallback to pure streaming if web search is globally disabled
    payload = {
        "model": config.MODEL_NAME,
        "messages": conversation.messages,
        "stream": True,
    }
    full_text, _, _ = await _stream_request(payload, on_token)
    conversation.add_assistant_text(full_text)
    return full_text