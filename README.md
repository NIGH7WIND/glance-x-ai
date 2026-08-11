# GlanceXAi

**A screen-anywhere AI overlay assistant.** Press a global hotkey, drag a box around anything on your screen, and GlanceXAi analyzes it in context and streams back a focused answer right where you're working.

---

## Features

- 🔥 **Instant AI summaries** — drag-select any screen region for a context-aware answer
- 🖼️ **Full-screen context** — the model sees both your crop and the full screenshot to infer what you're doing
- 🌍 **Agentic web search** — optional Tavily-powered search for real-time info
- 🗣️ **Streaming text-to-speech** — the response is spoken aloud as it streams
- ⌨️ **Global hotkeys** — trigger and dismiss from anywhere, no window focus needed

---

## How It Works

1. **Trigger** — Press `Ctrl+Alt+Shift` anywhere to open a fullscreen selection overlay.
2. **Select** — Drag a box around anything on screen (an error, a price, a chart, a form field…).
3. **Capture** — GlanceXAi captures the full screenshot and your crop.
4. **Analyze** — A local vision-language model (llama.cpp) processes both images.
5. **Stream** — The answer streams into a "Spotlight" popup next to your selection, spoken aloud as it arrives.
6. **Follow-up** — Continue the conversation directly in the popup.

---

## Architecture

```
hotkey.py ──▶ ui/drag_overlay ──▶ capture.py
                                       │
                                       ▼
                                    main.py ──▶ api_client.py ──▶ llama.cpp (OpenAI API)
                                       │              │
                                       │              ▼
                                       │        web_search.py (Tavily, optional)
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
              ui/spotlight                           tts_engine.py
              (text output)                          (audio playback)
```

| File | Responsibility |
|---|---|
| `main.py` | App bootstrap, Qt + qasync event loop, hotkey wiring, orchestration |
| `capture.py` | Multi-monitor screen capture, cropping, downscaling |
| `api_client.py` | Streaming OpenAI-compatible client with tool-calling |
| `web_search.py` | Async Tavily search integration |
| `hotkey.py` | Global hotkey listener (`pynput`) |
| `ui/` | PyQt6 widgets — `drag_overlay` (selection), `spotlight` (result popup) |
| `tts_engine.py` | Streaming text-to-speech playback |
| `config.py` | Central configuration (hotkeys, model, prompts) |

---

## Prerequisites

- Python 3.10+
- A running llama.cpp server exposing an OpenAI-compatible `/v1/chat/completions` endpoint with a vision-capable model
- *(Optional)* A Tavily API key for web search

---

## Installation

```bash
# Clone
git clone https://github.com/NIGH7WIND/glancexai.git
cd glancexai

# Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start your local llama.cpp server (vision model)
# llama-server -m path/to/vision-model.gguf --port 8080

# Optional: enable web search
echo "TAVILY_API_KEY=your_key_here" > .env
```

> GlanceXAi expects the llama.cpp server at `http://localhost:8080/v1/chat/completions` by default. Change this in `config.py`.

---

## Usage

```bash
python main.py
```

1. Press `Ctrl+Alt+Shift` to open the selection overlay.
2. Drag a box around what you want analyzed.
3. The Spotlight popup streams the answer next to your selection.
4. Type a follow-up in the popup to continue the conversation.
5. Press `Escape` to close the popup, or `Ctrl+Alt+-` to exit the app.

---

<p align="center">Made with ❤️ — select anything, understand everything.</p>