import asyncio
import json
import logging

import httpx

import config
from logging_setup import setup_logging

setup_logging()
logger = logging.getLogger("overlay_assistant.api_client")


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


async def stream_reply(conversation: Conversation, on_token):
    """
    Streams the model's reply for the current conversation state.
    on_token(str) is called for each incoming text chunk.
    Returns the full assembled text.
    """
    payload = {
        "model": config.MODEL_NAME,
        "messages": conversation.messages,
        "stream": True,
    }
    full_text = ""

    message_count = len(conversation.messages)
    logger.info(
        "stream_reply: start model=%s messages=%s url=%s",
        config.MODEL_NAME,
        message_count,
        config.LLAMA_SERVER_URL,
    )

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", config.LLAMA_SERVER_URL, json=payload) as resp:
            logger.info("stream_reply: http status=%s", resp.status_code)

            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                body = await resp.aread()
                logger.error("stream_reply: HTTP error status=%s body=%r", resp.status_code, body[:500])
                raise

            try:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = line[len("data: ") :]
                    if data.strip() == "[DONE]":
                        logger.info("stream_reply: received [DONE]")
                        await resp.aclose()
                        break

                    try:
                        chunk = json.loads(data)
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                    except Exception:
                        logger.exception("stream_reply: failed parsing stream chunk: %r", data[:300])
                        continue

                    if delta:
                        full_text += delta
                        on_token(delta)

            except asyncio.CancelledError:
                logger.info("stream_reply: cancelled")
                await resp.aclose()
                raise

            except Exception:
                logger.exception("stream_reply: streaming failed")
                raise

    conversation.add_assistant_text(full_text)
    logger.info("stream_reply: done full_text_len=%s", len(full_text))
    return full_text
