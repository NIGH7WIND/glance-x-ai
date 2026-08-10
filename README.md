# GlanceXAi

**A screen-anywhere AI overlay assistant.** Press a global hotkey, drag a box around anything on your screen — a stack trace, a price, a chart, a form field — and GlanceXAi instantly analyzes it using the full screenshot as context, streaming a focused, actionable answer right where you're working.

---

## ✨ Features

- 🔥 **Instant AI summaries** — drag-select any region of the screen and get a context-aware answer in seconds
- 🖼️ **Full-screen context** — the model sees both your highlighted crop _and_ the entire screen to infer what you're actually doing
- 🌍 **Agentic web search** — optional Tavily-powered real-time search for up-to-date information (news, prices, current events)
- 🗣️ **Streaming Text-to-Speech** — hear the AI's response spoken aloud as it streams.
- ⌨️ **Global hotkeys** — trigger and exit from anywhere, no window focus needed

---

## 🧠 How It Works

1. **Trigger** — Press `Ctrl+Alt+Shift` anywhere. A dimmed, fullscreen overlay appears.
2. **Select** — Drag a box around anything on your screen (a code error, a product price, a chart, a form field…).
3. **Capture** — GlanceXAi captures the full screenshot _and_ your highlighted crop, downscaling both for efficient context.
4. **Analyze** — A local vision-language model (llama.cpp) receives both images and infers what task you're in the middle of.
5. **Stream** — A focused, actionable answer streams into a borderless "Spotlight" popup next to your selection.
6. **Follow-up** — Ask a follow-up question right in the popup to dig deeper. The conversation stays in context, and the response is spoken aloud.

---

## 🏗️ Architecture

```
┌─────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  hotkey.py  │──▶│  ui/drag_overlay │──▶│    capture.py    │
│  (pynput)   │   │   (selection)    │   │ (screen + crop)  │
└─────────────┘   └──────────────────┘   └────────┬─────────┘
                           │                      ▼
                           │             ┌──────────────────┐
                           │             │  (llama.cpp via  │
                           │             │   OpenAI API)    │
                           │             └──────────────────┘
                           │                      ▲
                           │                      │
                           │             ┌──────────────────┐
                           │             │   web_search.py  │  (Tavily, optional)
                           │             └──────────────────┘
                           │                      ▲
                           │                      │
        ┌──────────────────┐   ┌────────┴─────────┐
        │     main.py      │──▶│   api_client.py  │
        │ (orchestration)  │   │ (streaming +     │
        │                  │   │  tool calling)   │
        └────────┬─────────┘   └──────────────────┘
                 │
                 ├───────────────────▶ ┌──────────────────┐
                 │                   │ │ ui/spotlight     │
                 │                   │ │  (text output)   │
                 │                   └─┴──────────────────┘
                 │
                 └───────────────────▶ ┌──────────────────┐
                                     │ │   tts_engine.py  │
                                     │ │ (audio playback) │
                                     └─┴──────────────────┘
```

- **`main.py`** — App bootstrap, Qt + qasync event loop, hotkey wiring, task orchestration
- **`capture.py`** — Multi-monitor screen capture, cropping, and intelligent downscaling
- **`api_client.py`** — Streaming OpenAI-compatible client with agentic tool-calling support
- **`web_search.py`** — Asynchronous Tavily search integration
- **`hotkey.py`** — Global hotkey listener via `pynput`
- **`ui/`** — PyQt6 widgets: `drag_overlay` (selection) and `spotlight` (result popup)
- **`config.py`** — Central configuration (hotkeys, model, prompts, settings)

---

## 📋 Prerequisites

- **Python 3.10+**
- **A running llama.cpp server** exposing an OpenAI-compatible `/v1/chat/completions` endpoint with a **vision-capable model** (e.g., a multimodal model like LLaVA / Gemma vision variants)
- _(Optional)_ A **Tavily API key** for agentic web search

---

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/NIGH7WIND/glancexai.git
cd glancexai

# 2. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start your local llama.cpp server (vision model)
#    Example (adjust to your setup):
#    llama-server -m path/to/vision-model.gguf --port 8080

# 5. Configure environment (optional)
#    Create a .env file at the project root and add your TAVILY_API_KEY:
#    echo "TAVILY_API_KEY=your_key_here" > .env
```

> **Note:** GlanceXAi expects the llama.cpp server at `http://localhost:8080/v1/chat/completions` by default. You can change this in `config.py`.

---

## 🎮 Usage

1. **Run the app:**

```bash
python main.py
```

2. **Trigger the overlay** — Press `Ctrl+Alt+Shift`. A dimmed, fullscreen selection overlay appears.

3. **Select a region** — Drag a box around anything you want analyzed. Release the mouse to capture.

4. **Get your answer** — The Spotlight popup appears next to your selection and streams the AI's response.

5. **Ask follow-ups** — Type into the popup's input box and press `Enter` to continue the conversation in context.

6. **Dismiss** — Press `Escape` to close the popup, or `Ctrl+Alt+-` to fully exit the app.

> **Web search:** When enabled, the model can autonomously trigger a web search when your question needs real-time info (indicated by a 🔍 _Searching…_ status in the popup).

---

<p align="center">Made with ❤️ — select anything, understand everything.</p>
