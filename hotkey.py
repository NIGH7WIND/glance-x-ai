import logging

from pynput import keyboard

import config
from logging_setup import setup_logging

setup_logging()
logger = logging.getLogger("overlay_assistant.hotkey")


class HotkeyListener:
    """Listens globally for a given hotkey and invokes a callback."""

    def __init__(self, on_trigger, hotkey: str):
        self.on_trigger = on_trigger
        logger.info("HotkeyListener init HOTKEY=%s", hotkey)
        self._hotkey = keyboard.HotKey(keyboard.HotKey.parse(hotkey), self._fire)
        self._listener = keyboard.Listener(
            on_press=self._for_canonical(self._hotkey.press),
            on_release=self._for_canonical(self._hotkey.release),
        )

    def _for_canonical(self, f):
        return lambda k: f(self._listener.canonical(k))

    def _fire(self):
        logger.info("Hotkey fired")
        self.on_trigger()

    def start(self):
        logger.info("HotkeyListener start")
        self._listener.start()

    def stop(self):
        logger.info("HotkeyListener stop")
        self._listener.stop()
