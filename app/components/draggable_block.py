from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QColor
from app.components.ConnectionLine import TemporaryDragLine

class DraggableBlock(QLabel):
    def __init__(self, step_id, step_data, parent=None):
        super().__init__(step_id, parent)
        self.step_id = step_id
        self.step_data = step_data
        self.setObjectName("DraggableBlock")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._base_width = 150
        self._base_height = 80
        self._scale = 1.0
        self.setFixedSize(self._base_width, self._base_height)
        self.setProperty("selected", False)
        self._drag_offset = None
        self._drag_moved = False
        self._hovered = False
        self.setMouseTracking(True)
        self._drag_line_active = False
        self._drag_line = None
        self.on_block_click = None
        self.on_connect_blocks = None
        self.on_context_menu = None
        self.root = None
        self._drag_over_target = None
        self._active_dot_index = None

    def set_scale(self, scale: float) -> None:
        if not scale or scale <= 0:
            return
        self._scale = scale
        w = max(60, int(self._base_width * scale))
        h = max(40, int(self._base_height * scale))
        self.setFixedSize(w, h)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._dot_hit_center(event.position().toPoint())
            if hit:
                start_center, dot_index = hit
                self._active_dot_index = dot_index
                self._start_drag_line(start_center)
            else:
                self._drag_offset = event.position().toPoint()
        if self.on_block_click:
            self.on_block_click(event)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._drag_line_active and (event.buttons() & Qt.MouseButton.LeftButton):
            end_point = self.mapToParent(event.position().toPoint())
            if self._drag_line:
                self._drag_line.update_end(end_point)
            self._update_drag_over_target(end_point)
        elif event.buttons() & Qt.MouseButton.LeftButton and self._drag_offset:
            new_pos = self.mapToParent(event.position().toPoint() - self._drag_offset)
            self.move(new_pos)
            self._drag_moved = True
            
            # Update connection lines if parent has them
            if self.parent():
                from app.components.ConnectionLine import ConnectionLine
                for child in self.parent().children():
                    if isinstance(child, ConnectionLine):
                        child.update_position()
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_line_active:
            end_point = self.mapToParent(event.position().toPoint())
            self._stop_drag_line()
            target = self._find_target_block(end_point)
            if target and self.on_connect_blocks:
                self.on_connect_blocks(self.step_id, target.step_id, self._active_dot_index, end_point)
            self._clear_drag_over_target()
            self._active_dot_index = None
        self._drag_offset = None
        if self._drag_moved and self.root and hasattr(self.root, "on_block_moved"):
            self.root.on_block_moved(self)
        self._drag_moved = False
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.on_context_menu:
            self.on_context_menu(event)
            event.accept()
            return
        super().contextMenuEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.raise_()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._hovered:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#8b5cf6"))

        for center in self._dot_centers():
            painter.drawEllipse(center.x() - self._dot_radius(),
                                center.y() - self._dot_radius(),
                                self._dot_radius() * 2,
                                self._dot_radius() * 2)

    def _dot_radius(self) -> int:
        return 3

    def _dot_hit_radius(self) -> int:
        return 10

    def _dot_centers(self):
        cx = self.width() // 2
        cy = self.height() // 2
        r = self._dot_radius()
        inset = r + 1
        return [
            QPoint(cx, inset),
            QPoint(self.width() - inset, cy),
            QPoint(cx, self.height() - inset),
            QPoint(inset, cy),
        ]

    def _dot_hit_center(self, pos: QPoint):
        radius = self._dot_hit_radius()
        r2 = radius * radius
        for index, center in enumerate(self._dot_centers()):
            dx = pos.x() - center.x()
            dy = pos.y() - center.y()
            if (dx * dx + dy * dy) <= r2:
                return center, index
        return None

    def _start_drag_line(self, local_center: QPoint):
        if not self.parent():
            return
        start_point = self.mapToParent(local_center)
        self._drag_line = TemporaryDragLine(start_point, parent=self.parent())
        self._drag_line_active = True

    def _stop_drag_line(self):
        if self._drag_line:
            self._drag_line.deleteLater()
        self._drag_line = None
        self._drag_line_active = False

    def _find_target_block(self, parent_pos: QPoint):
        if not self.root:
            return None
        for block in self.root.blocks.values():
            if block is self:
                continue
            if block.geometry().contains(parent_pos):
                return block
        return None

    def get_dot_centers_parent(self):
        centers = []
        for center in self._dot_centers():
            centers.append(self.mapToParent(center))
        return centers

    def nearest_dot_index(self, parent_pos: QPoint) -> int:
        centers = self.get_dot_centers_parent()
        if not centers:
            return 0
        best_index = 0
        best_dist = None
        for i, center in enumerate(centers):
            dx = parent_pos.x() - center.x()
            dy = parent_pos.y() - center.y()
            dist = dx * dx + dy * dy
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_index = i
        return best_index

    def _update_drag_over_target(self, parent_pos: QPoint):
        target = self._find_target_block(parent_pos)
        if target is self._drag_over_target:
            return
        if self._drag_over_target:
            self._drag_over_target.setProperty("dragOver", False)
            self._drag_over_target.style().unpolish(self._drag_over_target)
            self._drag_over_target.style().polish(self._drag_over_target)
            self._drag_over_target.update()
        self._drag_over_target = target
        if self._drag_over_target:
            self._drag_over_target.setProperty("dragOver", True)
            self._drag_over_target.style().unpolish(self._drag_over_target)
            self._drag_over_target.style().polish(self._drag_over_target)
            self._drag_over_target.update()

    def _clear_drag_over_target(self):
        if not self._drag_over_target:
            return
        self._drag_over_target.setProperty("dragOver", False)
        self._drag_over_target.style().unpolish(self._drag_over_target)
        self._drag_over_target.style().polish(self._drag_over_target)
        self._drag_over_target.update()
        self._drag_over_target = None
