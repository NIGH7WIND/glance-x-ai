import json
import httpx
import config


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
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", config.LLAMA_SERVER_URL, json=payload) as resp:
            try:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data.strip() == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        full_text += delta
                        on_token(delta)
            except asyncio.CancelledError:
                await resp.aclose()
                raise

    conversation.add_assistant_text(full_text)
    return full_text
