from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen


class DragOverlay(QWidget):
    """Fullscreen dimmed overlay for dragging a selection box."""

    selection_made = pyqtSignal(QRect)  # emits global screen-coords rect

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._start = None
        self._current = None

    def show_fullscreen_all_monitors(self, virtual_geometry: QRect):
        self.setGeometry(virtual_geometry)
        self._start = None
        self._current = None
        self.showFullScreen()
        self.activateWindow()

    def mousePressEvent(self, event):
        self._start = event.globalPosition().toPoint()
        self._current = self._start
        self.update()

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._current = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._start is None:
            return
        end = event.globalPosition().toPoint()
        rect = QRect(self._start, end).normalized()
        self.hide()
        if rect.width() > 4 and rect.height() > 4:
            self.selection_made.emit(rect)
        self._start = None
        self._current = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._start = None
            self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self._start and self._current:
            rect = QRect(self._start, self._current).normalized()
            # Translate global coords to widget-local coords
            local = QRect(self.mapFromGlobal(rect.topLeft()), rect.size())
            painter.fillRect(local, QColor(255, 255, 255, 40))
            pen = QPen(QColor(0, 170, 255), 2)
            painter.setPen(pen)
            painter.drawRect(local)
