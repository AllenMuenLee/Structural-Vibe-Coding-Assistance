from PyQt6.QtWidgets import QWidget
import math
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QPainterPathStroker
from PyQt6.QtCore import Qt, QPoint, QPointF


class TemporaryDragLine(QWidget):
    """Draws a temporary line from a start point to the cursor while dragging."""

    def __init__(self, start_point: QPoint, parent=None):
        super().__init__(parent)
        self.start = QPoint(start_point)
        self.end = QPoint(start_point)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if parent:
            self.setGeometry(parent.rect())
        self.show()

    def update_end(self, end_point: QPoint):
        self.end = QPoint(end_point)
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#8b5cf6"), 2)
        painter.setPen(pen)
        painter.drawLine(self.start, self.end)

class ConnectionLine(QWidget):
    """Draws an arrow between two blocks."""
    
    def __init__(
        self,
        from_block,
        to_block,
        parent=None,
        from_dot_index=None,
        to_dot_index=None,
        root=None,
        from_id=None,
        to_id=None,
    ):
        super().__init__(parent)
        self.from_block = from_block
        self.to_block = to_block
        self.from_dot_index = from_dot_index
        self.to_dot_index = to_dot_index
        self.root = root
        self.from_id = from_id
        self.to_id = to_id
        self._hovered = False
        # Curve tuning (adjust these to change how "curvy" the line is).
        self.curve_min_strength = 20.0
        self.curve_strength_factor = 0.1
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.update_position()
    
    def update_position(self):
        """Update line position based on block positions."""
        if not self.from_block or not self.to_block:
            return
        
        # Get anchor points (dot centers in parent coords when available)
        from_center = self._get_from_point()
        to_center = self._get_to_point()
        c1, c2 = self._control_points_parent(from_center, to_center)
        
        # Set widget geometry to cover both points with padding for hit-testing
        x = min(from_center.x(), to_center.x(), c1.x(), c2.x())
        y = min(from_center.y(), to_center.y(), c1.y(), c2.y())
        max_x = max(from_center.x(), to_center.x(), c1.x(), c2.x())
        max_y = max(from_center.y(), to_center.y(), c1.y(), c2.y())
        w = max_x - x
        h = max_y - y
        pad = 8
        self.setGeometry(
            int(x - pad),
            int(y - pad),
            int(w + pad * 2),
            int(h + pad * 2),
        )
        self.update()
    
    def paintEvent(self, event):
        """Draw the arrow."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen = QPen(QColor("#60a5fa"), 2)  # Blue arrow
        painter.setPen(pen)
        
        start, c1, c2, end = self._curve_points()
        path = QPainterPath()
        path.moveTo(start)
        path.cubicTo(c1, c2, end)
        painter.drawPath(path)


        if self._hovered:
            mid = self._curve_midpoint().toPoint()
            self._draw_delete_x(painter, mid)

    def _get_from_point(self) -> QPoint:
        if self.from_dot_index is not None and hasattr(self.from_block, "get_dot_centers_parent"):
            centers = self.from_block.get_dot_centers_parent()
            if 0 <= self.from_dot_index < len(centers):
                return centers[self.from_dot_index]
        return self.from_block.geometry().center()

    def _get_to_point(self) -> QPoint:
        if self.to_dot_index is not None and hasattr(self.to_block, "get_dot_centers_parent"):
            centers = self.to_block.get_dot_centers_parent()
            if 0 <= self.to_dot_index < len(centers):
                return centers[self.to_dot_index]
        return self.to_block.geometry().center()

    def _draw_delete_x(self, painter: QPainter, center: QPoint):
        size = 6
        pen = QPen(QColor("#f472b6"), 2)
        painter.setPen(pen)
        painter.drawLine(center.x() - size, center.y() - size, center.x() + size, center.y() + size)
        painter.drawLine(center.x() - size, center.y() + size, center.x() + size, center.y() - size)

    def _delete_hit_radius(self) -> int:
        return 9

    def _delete_center(self) -> QPoint:
        return self._curve_midpoint().toPoint()

    def _is_over_delete(self, pos: QPoint) -> bool:
        center = self._delete_center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        return (dx * dx + dy * dy) <= (self._delete_hit_radius() ** 2)

    def _is_near_line(self, pos: QPoint) -> bool:
        start, c1, c2, end = self._curve_points()
        path = QPainterPath()
        path.moveTo(start)
        path.cubicTo(c1, c2, end)

        stroker = QPainterPathStroker()
        line_width = 2.0
        hit_width = line_width * 1.5
        stroker.setWidth(hit_width)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        hit_path = stroker.createStroke(path)
        return hit_path.contains(pos.toPointF())

    def _dot_side(self, dot_index: int) -> str:
        mapping = {0: "top", 1: "right", 2: "bottom", 3: "left"}
        return mapping.get(dot_index, "bottom")

    def _control_points_parent(self, start: QPoint, end: QPoint):
        start_side = self._dot_side(self.from_dot_index)
        end_side = self._dot_side(self.to_dot_index)

        dx = abs(end.x() - start.x())
        dy = abs(end.y() - start.y())
        strength = max(
            float(self.curve_min_strength),
            (dx + dy) * float(self.curve_strength_factor),
        )

        vectors = {
            "top": QPointF(0, -1),
            "bottom": QPointF(0, 1),
            "left": QPointF(-1, 0),
            "right": QPointF(1, 0),
        }

        v1 = vectors.get(start_side, QPointF(0, 1))
        v2 = vectors.get(end_side, QPointF(0, -1))
        cp1 = QPointF(start.x(), start.y()) + (v1 * strength)
        cp2 = QPointF(end.x(), end.y()) + (v2 * strength)
        return cp1, cp2

    def _curve_points(self):
        from_center = self._get_from_point()
        to_center = self._get_to_point()
        start = QPointF(from_center.x() - self.x(), from_center.y() - self.y())
        end = QPointF(to_center.x() - self.x(), to_center.y() - self.y())
        c1_parent, c2_parent = self._control_points_parent(from_center, to_center)
        c1 = QPointF(c1_parent.x() - self.x(), c1_parent.y() - self.y())
        c2 = QPointF(c2_parent.x() - self.x(), c2_parent.y() - self.y())
        return start, c1, c2, end

    def _curve_midpoint(self) -> QPointF:
        start, c1, c2, end = self._curve_points()
        t = 0.5
        inv = 1.0 - t
        x = (
            inv * inv * inv * start.x()
            + 3 * inv * inv * t * c1.x()
            + 3 * inv * t * t * c2.x()
            + t * t * t * end.x()
        )
        y = (
            inv * inv * inv * start.y()
            + 3 * inv * inv * t * c1.y()
            + 3 * inv * t * t * c2.y()
            + t * t * t * end.y()
        )
        return QPointF(x, y)

    def enterEvent(self, event):
        try:
            pos = event.position().toPoint()
            near = self._is_near_line(pos) or self._is_over_delete(pos)
        except AttributeError:
            near = False
        self._hovered = near
        if self._hovered:
            self.update()
        super().enterEvent(event)

    def hoverEnterEvent(self, event):
        pos = event.position().toPoint()
        near = self._is_near_line(pos) or self._is_over_delete(pos)
        if near != self._hovered:
            self._hovered = near
            self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        pos = event.position().toPoint()
        near = self._is_near_line(pos) or self._is_over_delete(pos)
        if near != self._hovered:
            self._hovered = near
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        if self._hovered:
            self._hovered = False
            self.update()
        super().hoverLeaveEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        near = self._is_near_line(pos) or self._is_over_delete(pos)
        if near != self._hovered:
            self._hovered = near
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and self._is_over_delete(pos):
            if self.root and self.from_id and self.to_id:
                remove_fn = getattr(self.root, "remove_connection", None)
                if remove_fn:
                    remove_fn(self.from_id, self.to_id)
            event.accept()
            return
        if not self._is_near_line(pos):
            event.ignore()
            return
        super().mousePressEvent(event)
