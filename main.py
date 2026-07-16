import asyncio
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect, QObject, pyqtSignal
import qasync

import config
from hotkey import HotkeyListener
from capture import capture_full_and_crop
from api_client import Conversation, stream_reply
from ui.drag_overlay import DragOverlay
from ui.spotlight import Spotlight


class _HotkeyBridge(QObject):
    """pynput fires on its own thread; re-emit on the Qt thread via signal."""
    triggered = pyqtSignal()


class App:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.loop = qasync.QEventLoop(self.qt_app)
        asyncio.set_event_loop(self.loop)

        self.drag_overlay = DragOverlay()
        self.spotlight = Spotlight()
        self.conversation: Conversation | None = None
        self._pending_query: str | None = None
        self._streaming = False

        self.drag_overlay.selection_made.connect(self._on_selection_made)
        self.spotlight.query_submitted.connect(self._on_query_submitted)
        self.spotlight.dismissed.connect(self._cancel_active_task)

        self._bridge = _HotkeyBridge()
        self._bridge.triggered.connect(self._show_drag_overlay)
        self.hotkey = HotkeyListener(self._bridge.triggered.emit)

        self._active_task: asyncio.Task | None = None

    def _cancel_active_task(self):
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()
        self._active_task = None

    def _show_drag_overlay(self):
        virtual_geometry = self.qt_app.primaryScreen().virtualGeometry()
        self.drag_overlay.show_fullscreen_all_monitors(virtual_geometry)

    def _on_selection_made(self, rect: QRect):
        self._cancel_active_task()
        screen = self.qt_app.screenAt(rect.center())
        dpr = screen.devicePixelRatio()
        bbox = (
            int(rect.left() * dpr),
            int(rect.top() * dpr),
            int(rect.right() * dpr),
            int(rect.bottom() * dpr),
        )
        screen_geo = screen.availableGeometry()
        self.spotlight.open_at(rect.left(), rect.bottom() + 8, screen_geo)
        self.conversation = None  # fresh session
        self._active_task = asyncio.ensure_future(self._run_summary(bbox))

    async def _run_summary(self, bbox):
        full_b64, crop_b64 = capture_full_and_crop(bbox)
        self.conversation = Conversation(full_b64, crop_b64)
        self._streaming = True
        await stream_reply(self.conversation, self.spotlight.append_summary_token)
        self._streaming = False
        if self._pending_query:
            q = self._pending_query
            self._pending_query = None
            await self._run_followup(q)

    def _on_query_submitted(self, text: str):
        if self.conversation is None:
            return
        if self._streaming:
            self._pending_query = text
            return
        asyncio.ensure_future(self._run_followup(text))

    async def _run_followup(self, text: str):
        self.conversation.add_user_text(text)
        self.spotlight.summary_label.setText(self.spotlight.summary_label.text() + "\n\n")
        self._streaming = True
        await stream_reply(self.conversation, self.spotlight.append_summary_token)
        self._streaming = False

    def run(self):
        self.hotkey.start()
        with self.loop:
            self.loop.run_forever()


if __name__ == "__main__":
    app = App()
    app.run()