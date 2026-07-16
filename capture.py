import base64
import io
import logging

import mss
from PIL import Image

import config
from logging_setup import setup_logging

setup_logging()
logger = logging.getLogger("overlay_assistant.capture")


def _downscale(img: Image.Image, max_dim: int) -> Image.Image:
    w, h = img.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def _to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def capture_full_and_crop(bbox: tuple[int, int, int, int]) -> tuple[str, str]:
    """
    bbox: (left, top, right, bottom) in virtual-screen coordinates.
    Returns (full_screenshot_b64, crop_b64), both PNG-encoded, downscaled.
    """
    left, top, right, bottom = bbox

    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # full virtual screen, all displays
            logger.debug(
                "capture: bbox=%s monitor_left_top=(%s,%s) monitor_size=%s",
                bbox,
                monitor.get("left"),
                monitor.get("top"),
                monitor.get("width"),
            )

            raw = sct.grab(monitor)
            full_img = Image.frombytes("RGB", raw.size, raw.rgb)

        # bbox coords are relative to monitor origin; adjust if monitor origin != 0,0
        mx, my = monitor["left"], monitor["top"]
        crop_box = (left - mx, top - my, right - mx, bottom - my)
        logger.debug("capture: crop_box=%s full_size=%s", crop_box, full_img.size)

        crop_img = full_img.crop(crop_box)

        full_small = _downscale(full_img, config.FULL_SCREENSHOT_MAX_DIM)
        crop_full = _downscale(crop_img, config.CROP_MAX_DIM)

        logger.info(
            "capture: downscaled full=%s crop=%s",
            full_small.size,
            crop_full.size,
        )

        return _to_b64(full_small), _to_b64(crop_full)
    except Exception:
        logger.exception("capture failed: bbox=%s", bbox)
        raise
