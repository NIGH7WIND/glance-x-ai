from pynput import keyboard
import config


class HotkeyListener:
    """Listens globally for HOTKEY and invokes a callback."""

    def __init__(self, on_trigger):
        self.on_trigger = on_trigger
        self._hotkey = keyboard.HotKey(
            keyboard.HotKey.parse(config.HOTKEY), self._fire
        )
        self._listener = keyboard.Listener(
            on_press=self._for_canonical(self._hotkey.press),
            on_release=self._for_canonical(self._hotkey.release),
        )

    def _for_canonical(self, f):
        return lambda k: f(self._listener.canonical(k))

    def _fire(self):
        self.on_trigger()

    def start(self):
        self._listener.start()

    def stop(self):
        self._listener.stop()
