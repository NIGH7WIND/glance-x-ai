HOTKEY = "<ctrl>+<alt>+<space>"

LLAMA_SERVER_URL = "http://localhost:8080/v1/chat/completions"
MODEL_NAME = "gemma-4-e4b-it"

FULL_SCREENSHOT_MAX_DIM = 768   # downscale target for context image
CROP_MAX_DIM = 1024             # downscale target for focus crop

SUMMARY_SYSTEM_PROMPT = (
    "You are a screen overlay assistant. You are given two images: "
    "a full screenshot for context, and a cropped region the user highlighted. "
    "Describe what the highlighted region is and what it's for. "
    "Max 1-2 sentences unless asked to elaborate."
)
