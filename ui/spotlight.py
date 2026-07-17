import logging

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QLabel, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from logging_setup import setup_logging

setup_logging()
logger = logging.getLogger("overlay_assistant.ui.spotlight")


class Spotlight(QWidget):
    """Borderless always-on-top popup: streaming summary + follow-up input."""

    query_submitted = pyqtSignal(str)
    dismissed = pyqtSignal()

    # Used to log only once per streamed response.
    _logged_stream_start: bool

    def __init__(self):
        super().__init__()
        self._logged_stream_start = False
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.summary_label = QLabel("...")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "color: white; font-size: 14px; background: transparent; padding: 10px;"
        )

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.summary_label)
        self.scroll_area.setWidgetResizable(True)
        
        # --- SIZE ADJUSTMENTS ---
        self.scroll_area.setMinimumHeight(100)  # Ensures it never looks like a tiny slit
        self.scroll_area.setMaximumHeight(500)  # Increased from 320 to allow more text
        # ------------------------
        
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setStyleSheet(
            "background: rgba(30,30,30,220); border-radius: 8px;"
        )

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask a follow-up...")
        self.input.setStyleSheet(
            "color: white; font-size: 14px; background: rgba(20,20,20,230); "
            "border: 1px solid #555; border-radius: 6px; padding: 8px;"
        )
        self.input.returnPressed.connect(self._on_submit)

        layout.addWidget(self.scroll_area)
        layout.addWidget(self.input)

    def _on_submit(self):
        text = self.input.text().strip()
        if text:
            logger.info("Spotlight submit (len=%s)", len(text))
            self.query_submitted.emit(text)
            self.input.clear()

    def open_at(self, x: int, y: int, screen_geometry=None):
        self._logged_stream_start = False
        self.summary_label.setText("...")
        self.adjustSize()
        logger.info("Spotlight open_at x=%s y=%s", x, y)

        if screen_geometry is not None:
            margin = 12
            w = self.width()
            # Updated height calculation to respect the new larger sizes
            h = min(self.sizeHint().height(), 600)  
            max_x = screen_geometry.right() - w - margin
            max_y = screen_geometry.bottom() - h - margin
            x = max(screen_geometry.left() + margin, min(x, max_x))
            y = max(screen_geometry.top() + margin, min(y, max_y))

        self.move(x, y)
        self.show()
        self.activateWindow()
        self.raise_()
        QTimer.singleShot(0, self.input.setFocus)

    def append_summary_token(self, token: str):
        if self.summary_label.text() == "...":
            self.summary_label.setText("")
            if not self._logged_stream_start:
                logger.info("Spotlight streaming started")
                self._logged_stream_start = True

        self.summary_label.setText(self.summary_label.text() + token)
        
        # Dynamically expand the window height as new text streams in
        self.adjustSize() 
        
        # Auto-scroll to the bottom of the scroll area as text updates
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            logger.info("Spotlight dismissed via Escape")
            self.hide()
            self.dismissed.emit()

    def show_error(self, message: str):
        if self.summary_label.text() == "...":
            self.summary_label.setText("")
        self.summary_label.setText(
            self.summary_label.text() + f"\n\n[Error: {message}]"
        )
        self.adjustSize()
