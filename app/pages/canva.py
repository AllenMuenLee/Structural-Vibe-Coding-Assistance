import sys
import os
import json
from functools import partial
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QMessageBox,
    QTextEdit, QListWidget, QInputDialog, QMenu
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from app.components.draggable_block import DraggableBlock
from src.utils.CacheMng import load_cache
from src.utils.NetUtils import is_connection_error
from app.pages.loadingScreen import LoadingScreen
from app.components.ConnectionLine import ConnectionLine


CHILDREN_KEY = "children"
LEGACY_CHILDREN_KEY = "chlidren"


def _get_children(step_data):
    if not isinstance(step_data, dict):
        return []
    if CHILDREN_KEY in step_data:
        return step_data.get(CHILDREN_KEY, []) or []
    return step_data.get(LEGACY_CHILDREN_KEY, []) or []


def _set_children(step_data, children):
    if not isinstance(step_data, dict):
        return
    step_data[CHILDREN_KEY] = children
    if LEGACY_CHILDREN_KEY in step_data:
        step_data.pop(LEGACY_CHILDREN_KEY, None)


def _set_details_visible(root, visible: bool) -> None:
    panel = getattr(root, "details_panel_widget", None)
    if panel is not None:
        panel.setVisible(bool(visible))


def _build_parents_map(steps: dict) -> dict:
    parents = {sid: [] for sid in steps.keys()}
    for sid, data in steps.items():
        for cid in _get_children(data):
            if cid in parents:
                parents[cid].append(sid)
    return parents


def _find_root_ids(parents: dict, steps: dict, start_id: Optional[str]) -> list:
    roots = [sid for sid, ps in parents.items() if not ps]
    if start_id and start_id in steps:
        if start_id in roots:
            roots.remove(start_id)
        roots.insert(0, start_id)
    return roots or list(steps.keys())


def _assign_levels(parents: dict, steps: dict, start_id: Optional[str]) -> dict:
    level = {}
    queue = _find_root_ids(parents, steps, start_id)
    for rid in queue:
        level[rid] = 0
    idx = 0
    while idx < len(queue):
        current = queue[idx]
        idx += 1
        curr_level = level.get(current, 0)
        for child in _get_children(steps.get(current, {})):
            if child not in steps:
                continue
            next_level = max(level.get(child, -1), curr_level + 1)
            if level.get(child) != next_level:
                level[child] = next_level
            if child not in queue:
                queue.append(child)
    for sid in steps.keys():
        if sid not in level:
            level[sid] = 0
    return level


def _barycenter(node_id: str, parents: dict, index: dict) -> float:
    ps = parents.get(node_id, [])
    if not ps:
        return float(index.get(node_id, 0))
    vals = [index.get(p, 0) for p in ps if p in index]
    return sum(vals) / len(vals) if vals else 0.0


def _order_levels(levels: dict, parents: dict) -> dict:
    max_level = max(levels.values()) if levels else 0
    level_nodes = {i: [] for i in range(max_level + 1)}
    for sid, lvl in levels.items():
        level_nodes.setdefault(lvl, [])
        level_nodes[lvl].append(sid)

    for lvl in level_nodes:
        level_nodes[lvl].sort()

    for _ in range(4):
        for lvl in range(1, max_level + 1):
            prev = level_nodes.get(lvl - 1, [])
            if not prev:
                continue
            index = {sid: i for i, sid in enumerate(prev)}
            level_nodes[lvl].sort(key=lambda node_id: _barycenter(node_id, parents, index))
    return level_nodes


def _handle_block_click(root, step_id, step_data, event):
    on_block_click(root, step_id, step_data, event)


def _handle_block_context_menu(root, step_id, step_data, block, event):
    on_block_click(root, step_id, step_data, event)
    menu = QMenu(block)
    delete_action = menu.addAction("Delete Node")
    action = menu.exec(event.globalPos())
    if action == delete_action:
        root.selected_step_id = step_id
        on_delete_step(root)


def _handle_connect_blocks(root, from_id, to_id, from_dot_index, drop_pos):
    connect_blocks(root, from_id, to_id, from_dot_index, drop_pos)


def _handle_edit_generation_finished(root, loading, success, message, edits_text, edit_log):
    loading.close()
    if success:
        root.last_edits_text = edits_text
        root.last_edit_log = edit_log
        if not root.code_editor_engine:
            QMessageBox.critical(None, "Error", "Code editor engine not initialized.")
            return
        if not (edits_text or "").strip():
            QMessageBox.information(None, "No Edits", "No edits were generated.")
            return
        try:
            root.code_editor_engine.apply_edits(edits_text)
            project_root = ""
            if root.flowchart_data:
                project_root = root.flowchart_data.get("project_root", "")
            if project_root:
                from src.core.CodeEdt import CodeEditor
                root.code_editor_engine = CodeEditor(project_root)
            update_generate_button(root)
            QMessageBox.information(None, "Edits Applied", "Edits have been applied successfully.")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to apply edits: {e}")
    else:
        QMessageBox.critical(None, "Error", f"Failed to generate edits: {message}")


def _handle_code_generation_finished(root, loading, success, message):
    loading.close()
    if success:
        QMessageBox.information(None, "Success", message)
        root.code_generated = True
        update_generate_button(root)
        _call_on_code_generated(root)
    else:
        QMessageBox.critical(None, "Error", message)


class CanvasArea(QWidget):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self._root = root
        self._panning = False
        self._pan_start = None
        self._scroll_start = None
        self._pan_moved = False
        self._suppress_context = False

    def contextMenuEvent(self, event):
        if self._suppress_context:
            self._suppress_context = False
            event.accept()
            return
        if not self._root:
            return
        menu = QMenu(self)
        add_action = menu.addAction("Add Node")
        action = menu.exec(event.globalPos())
        if action == add_action:
            on_add_step(self._root)

    def wheelEvent(self, event):
        if not self._root:
            return super().wheelEvent(event)
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                _adjust_zoom(self._root, 1.1)
            elif delta < 0:
                _adjust_zoom(self._root, 0.9)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if not self._root:
            return super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.RightButton:
            scroll = getattr(self._root, "canvas_scroll", None)
            if scroll:
                self._panning = True
                self._pan_start = event.globalPosition().toPoint()
                h = scroll.horizontalScrollBar()
                v = scroll.verticalScrollBar()
                self._scroll_start = (h.value(), v.value())
                self._pan_moved = False
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start and self._scroll_start:
            scroll = getattr(self._root, "canvas_scroll", None)
            if scroll:
                delta = event.globalPosition().toPoint() - self._pan_start
                if not self._pan_moved and (abs(delta.x()) > 3 or abs(delta.y()) > 3):
                    self._pan_moved = True
                h = scroll.horizontalScrollBar()
                v = scroll.verticalScrollBar()
                h.setValue(self._scroll_start[0] - delta.x())
                v.setValue(self._scroll_start[1] - delta.y())
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            if self._pan_moved:
                self._suppress_context = True
            self._pan_start = None
            self._scroll_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


def build_canva(flowchart_data=None, on_back=None) -> QWidget:
    """Build the canvas page with flowchart visualization."""
    
    root = QWidget()
    root.setObjectName("CanvaPage")
    
    # Main horizontal layout: canvas on left, details on right
    main_layout = QHBoxLayout(root)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)
    
    # Left side: Canvas area
    left_container = QWidget()
    left_layout = QVBoxLayout(left_container)
    left_layout.setContentsMargins(10, 10, 10, 10)
    
    # Toolbar
    toolbar = QHBoxLayout()

    generate_btn = QPushButton("Generate Code")
    generate_btn.setObjectName("PrimaryButton")
    generate_btn.setToolTip("Generate code")
    generate_btn.clicked.connect(lambda: on_generate_code(root))

    open_editor_btn = QPushButton("Open Editor")
    open_editor_btn.setObjectName("ToolbarButton")
    open_editor_btn.setToolTip("Open code editor")
    open_editor_btn.clicked.connect(lambda: on_open_editor(root))
    open_editor_btn.hide()

    back_btn = QPushButton("Back")
    back_btn.setObjectName("BackButton")
    back_btn.setToolTip("Back")
    back_btn.setEnabled(on_back is not None)
    back_btn.clicked.connect(lambda: on_back() if on_back else None)
    
    toolbar.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    toolbar.addStretch()
    toolbar.addWidget(generate_btn)
    toolbar.addWidget(open_editor_btn)
    
    left_layout.addLayout(toolbar)
    
    # Canvas scroll area
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setObjectName("CanvasScroll")
    
    # ✅ BIGGER canvas for scrolling
    canvas = CanvasArea(root)
    canvas.setObjectName("Canvas")
    canvas.setMinimumSize(1400, 2500)  # ✅ Much taller
    
    scroll.setWidget(canvas)
    left_layout.addWidget(scroll)
    
    # Right side: Details panel
    details_panel = QWidget()
    details_panel.setObjectName("DetailsPanel")
    details_panel.setFixedWidth(350)
    details_layout = QVBoxLayout(details_panel)
    details_layout.setContentsMargins(20, 20, 20, 20)
    
    # Details panel title + close
    details_header = QHBoxLayout()
    details_title = QLabel("Step Details")
    details_title.setObjectName("DetailsPanelTitle")
    details_close_btn = QPushButton("X")
    details_close_btn.setObjectName("DetailsCloseButton")
    details_close_btn.setToolTip("Hide step details")
    details_close_btn.setFixedSize(24, 24)
    details_header.addWidget(details_title)
    details_header.addStretch()
    details_header.addWidget(details_close_btn)
    details_layout.addLayout(details_header)
    
    # Step ID (read-only)
    step_id_label = QLabel("Step ID:")
    step_id_label.setObjectName("DetailsLabel")
    details_layout.addWidget(step_id_label)
    
    step_id_value = QLabel("No step selected")
    step_id_value.setObjectName("StepIdValue")
    details_layout.addWidget(step_id_value)
    
    # Description
    desc_label = QLabel("Description:")
    desc_label.setObjectName("DetailsLabel")
    details_layout.addWidget(desc_label)
    
    desc_value = QTextEdit()
    desc_value.setObjectName("DescValue")
    desc_value.setReadOnly(False)
    desc_value.setPlaceholderText("Select a step to edit")
    desc_value.setMaximumHeight(100)
    details_layout.addWidget(desc_value)
    
    # Files
    files_label = QLabel("Files to Generate:")
    files_label.setObjectName("DetailsLabel")
    details_layout.addWidget(files_label)
    
    files_list = QListWidget()
    files_list.setObjectName("FilesList")
    files_list.setMaximumHeight(100)
    details_layout.addWidget(files_list)
    
    # File buttons
    file_buttons = QHBoxLayout()
    add_file_btn = QPushButton("Add File")
    remove_file_btn = QPushButton("Remove File")
    add_file_btn.setObjectName("MiniButton")
    remove_file_btn.setObjectName("MiniButton")
    add_file_btn.setToolTip("Add file")
    remove_file_btn.setToolTip("Remove file")
    add_file_btn.clicked.connect(lambda: on_add_file(root))
    remove_file_btn.clicked.connect(lambda: on_remove_file(root))
    file_buttons.addWidget(add_file_btn)
    file_buttons.addWidget(remove_file_btn)
    details_layout.addLayout(file_buttons)

    # Files to import
    imports_label = QLabel("Files to Import:")
    imports_label.setObjectName("DetailsLabel")
    details_layout.addWidget(imports_label)

    imports_list = QListWidget()
    imports_list.setObjectName("ImportsList")
    imports_list.setMaximumHeight(80)
    details_layout.addWidget(imports_list)

    import_buttons = QHBoxLayout()
    add_import_btn = QPushButton("Add Import")
    remove_import_btn = QPushButton("Remove Import")
    add_import_btn.setObjectName("MiniButton")
    remove_import_btn.setObjectName("MiniButton")
    add_import_btn.setToolTip("Add file to import")
    remove_import_btn.setToolTip("Remove import")
    add_import_btn.clicked.connect(lambda: on_add_import(root))
    remove_import_btn.clicked.connect(lambda: on_remove_import(root))
    import_buttons.addWidget(add_import_btn)
    import_buttons.addWidget(remove_import_btn)
    details_layout.addLayout(import_buttons)
    
    # ✅ Children/Connections editor
    children_label = QLabel("Next Steps (Children):")
    children_label.setObjectName("DetailsLabel")
    details_layout.addWidget(children_label)
    
    children_list = QListWidget()
    children_list.setObjectName("ChildrenList")
    children_list.setMaximumHeight(80)
    details_layout.addWidget(children_list)
    
    # Children buttons removed per new UX
    
    # Commands
    commands_label = QLabel("Commands:")
    commands_label.setObjectName("DetailsLabel")
    details_layout.addWidget(commands_label)
    
    commands_value = QTextEdit()
    commands_value.setObjectName("CommandsValue")
    commands_value.setReadOnly(False)
    commands_value.setMaximumHeight(80)
    commands_value.setPlaceholderText("One command per line")
    details_layout.addWidget(commands_value)
    
    # Save button
    save_btn = QPushButton("Save Changes")
    save_btn.setObjectName("SaveButton")
    save_btn.setToolTip("Save changes")
    save_btn.clicked.connect(lambda: on_save_changes(root))
    details_layout.addWidget(save_btn)
    
    details_layout.addStretch()
    
    # Add both sides to main layout
    main_layout.addWidget(left_container, stretch=1)
    main_layout.addWidget(details_panel)
    
    details_close_btn.clicked.connect(partial(_set_details_visible, root, False))

    # Store references
    root.canvas = canvas
    root.details_panel = {
        'step_id': step_id_value,
        'description': desc_value,
        'files': files_list,
        'imports': imports_list,
        'children': children_list,
        'commands': commands_value,
        'save_btn': save_btn
    }
    root.details_panel_widget = details_panel
    root.blocks = {}
    root.connections = []
    root.selected_step_id = None
    root.flowchart_data = flowchart_data
    root.code_generated = False
    root.generate_btn = generate_btn
    root.open_editor_btn = open_editor_btn
    root.remove_connection = lambda from_id, to_id: remove_connection(root, from_id, to_id)
    root.on_block_moved = lambda block: on_block_moved(root, block)
    root.zoom_factor = 1.0
    root._layout_positions = {}
    root._layout_size = (1400, 2500)
    root.canvas_scroll = scroll
    root._canvas_origin = (0.0, 0.0)

    if flowchart_data:
        project_root = flowchart_data.get("project_root", "")
        if project_root:
            from src.core.CodeEdt import CodeEditor
            root.code_editor_engine = CodeEditor(project_root)
        else:
            root.code_editor_engine = None
    else:
        root.code_editor_engine = None

    if flowchart_data:
        project_root = flowchart_data.get("project_root", "")
        if project_root:
            root.code_generated = _detect_code_generated(project_root)
            update_generate_button(root)
    
    if flowchart_data:
        load_flowchart(root, flowchart_data)

    return root


def _load_saved_positions(flowchart_data):
    raw = flowchart_data.get("layout_positions", {}) if flowchart_data else {}
    positions = {}
    if not isinstance(raw, dict):
        return positions
    for sid, value in raw.items():
        if isinstance(value, dict):
            x = value.get("x")
            y = value.get("y")
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            x, y = value[0], value[1]
        else:
            continue
        if x is None or y is None:
            continue
        try:
            positions[sid] = (float(x), float(y))
        except (TypeError, ValueError):
            continue
    return positions


def _persist_layout_positions(root):
    if not root or not getattr(root, "flowchart_data", None):
        return
    layout = {}
    for sid, pos in (getattr(root, "_layout_positions", {}) or {}).items():
        if not pos or len(pos) < 2:
            continue
        layout[sid] = [float(pos[0]), float(pos[1])]
    root.flowchart_data["layout_positions"] = layout
    save_flowchart_to_file(root.flowchart_data)


def _graph_bounds(root):
    positions = getattr(root, "_layout_positions", {}) or {}
    if positions:
        xs = [pos[0] for pos in positions.values() if pos and len(pos) >= 2]
        ys = [pos[1] for pos in positions.values() if pos and len(pos) >= 2]
    else:
        xs, ys = [], []

    if xs and ys:
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
    else:
        # Default center if nothing exists yet.
        min_x = max_x = 700
        min_y = max_y = 80

    # Expand by half block size to include edges.
    block_w = 150
    block_h = 80
    for block in getattr(root, "blocks", {}).values():
        scale = getattr(root, "zoom_factor", 1.0) or 1.0
        if scale > 0:
            block_w = block.width() / scale
            block_h = block.height() / scale
        break

    half_w = block_w / 2.0
    half_h = block_h / 2.0
    return (min_x - half_w, min_y - half_h, max_x + half_w, max_y + half_h)


def _ensure_canvas_fits_graph(root):
    if not root or not getattr(root, "canvas", None):
        return
    min_x, min_y, max_x, max_y = _graph_bounds(root)
    margin = 1200
    span_w = max_x - min_x
    span_h = max_y - min_y
    base_w = max(10000, int(span_w + margin * 2))
    base_h = max(10000, int(span_h + margin * 2))
    origin_x = min_x - margin
    origin_y = min_y - margin
    root._canvas_origin = (origin_x, origin_y)
    root._layout_size = (base_w, base_h)
    _apply_zoom(root)


def _center_view_on_graph(root):
    scroll = getattr(root, "canvas_scroll", None)
    if not scroll:
        return
    min_x, min_y, max_x, max_y = _graph_bounds(root)
    scale = getattr(root, "zoom_factor", 1.0) or 1.0
    origin_x, origin_y = getattr(root, "_canvas_origin", (0.0, 0.0))
    center_x = (((min_x + max_x) / 2.0) - origin_x) * scale
    center_y = (((min_y + max_y) / 2.0) - origin_y) * scale

    viewport = scroll.viewport().size()
    target_x = int(center_x - (viewport.width() / 2.0))
    target_y = int(center_y - (viewport.height() / 2.0))

    h = scroll.horizontalScrollBar()
    v = scroll.verticalScrollBar()
    h.setValue(max(0, min(target_x, h.maximum())))
    v.setValue(max(0, min(target_y, v.maximum())))


def load_flowchart(root, flowchart_data):
    """Load flowchart data and create visual blocks."""
    
    canvas = root.canvas
    steps = flowchart_data.get('steps', {})
    saved_positions = _load_saved_positions(flowchart_data)
    
    # Clear existing
    for block in root.blocks.values():
        block.deleteLater()
    for conn in root.connections:
        conn.deleteLater()
    
    root.blocks.clear()
    root.connections.clear()
    
    # Layered layout to reduce crossings and avoid lines over nodes
    start_id = flowchart_data.get('start_id')
    x_center = 700
    y_offset = 80
    left_pad = 240
    top_pad = 120
    x_spacing = 240  # block width 150 + padding
    y_spacing = 160  # block height 80 + padding

    positions = {}
    max_y = y_offset
    max_x = x_center

    parents = _build_parents_map(steps)
    levels = _assign_levels(parents, steps, start_id)
    ordered = _order_levels(levels, parents)

    for lvl, nodes_at_level in ordered.items():
        if not nodes_at_level:
            continue
        total_width = (len(nodes_at_level) - 1) * x_spacing
        start_x = x_center - total_width / 2
        y_pos = y_offset + lvl * y_spacing
        for i, sid in enumerate(nodes_at_level):
            x_pos = start_x + i * x_spacing
            positions[sid] = (x_pos + left_pad, y_pos + top_pad)
            max_x = max(max_x, x_pos)
            max_y = max(max_y, y_pos)

    if saved_positions:
        for sid, pos in saved_positions.items():
            if sid not in steps:
                continue
            positions[sid] = pos
            try:
                max_x = max(max_x, float(pos[0]) - left_pad)
                max_y = max(max_y, float(pos[1]) - top_pad)
            except (TypeError, ValueError):
                continue
    
    # ✅ Resize canvas dynamically
    root._layout_positions = positions
    _ensure_canvas_fits_graph(root)
    
    # Create blocks
    for step_id, step_data in steps.items():
        block = DraggableBlock(step_id, step_data, parent=canvas)
        _place_block(root, block, step_id, x_center, y_offset)
        block.show()
        
        block.on_block_click = partial(_handle_block_click, root, step_id, step_data)
        block.on_context_menu = partial(
            _handle_block_context_menu, root, step_id, step_data, block
        )
        block.on_connect_blocks = partial(_handle_connect_blocks, root)
        block.root = root
        root.blocks[step_id] = block
    
    # Draw connections
    for step_id, step_data in steps.items():
        from_block = root.blocks.get(step_id)
        if not from_block:
            continue
        
        children = _get_children(step_data)
        for child_id in children:
            to_block = root.blocks.get(child_id)
            if to_block:
                meta = step_data.get("connection_meta", {}).get(child_id, {})
                from_dot_index = meta.get("from_dot")
                to_dot_index = meta.get("to_dot")
                if from_dot_index is None:
                    from_dot_index = 2  # bottom
                if to_dot_index is None:
                    to_dot_index = 0  # top
                line = ConnectionLine(
                    from_block,
                    to_block,
                    parent=canvas,
                    from_dot_index=from_dot_index,
                    to_dot_index=to_dot_index,
                    root=root,
                    from_id=step_id,
                    to_id=child_id,
                )
                line.lower()
                line.show()
                root.connections.append(line)

    _refresh_connections(root)
    QTimer.singleShot(0, lambda: _center_view_on_graph(root))


def _place_block(root, block, step_id, default_x, default_y):
    scale = getattr(root, "zoom_factor", 1.0) or 1.0
    block.set_scale(scale)
    positions = getattr(root, "_layout_positions", {}) or {}
    origin_x, origin_y = getattr(root, "_canvas_origin", (0.0, 0.0))
    if step_id in positions:
        x_pos, y_pos = positions[step_id]
    else:
        x_pos, y_pos = default_x, default_y
    w = block.width()
    h = block.height()
    block.move(
        int((x_pos - origin_x) * scale - (w / 2)),
        int((y_pos - origin_y) * scale - (h / 2)),
    )


def _apply_zoom(root):
    scale = getattr(root, "zoom_factor", 1.0) or 1.0
    base_w, base_h = getattr(root, "_layout_size", (1400, 2500))
    root.canvas.setMinimumSize(int(base_w * scale), int(base_h * scale))
    for step_id, block in root.blocks.items():
        _place_block(root, block, step_id, 600, 50)
    _refresh_connections(root)


def _adjust_zoom(root, factor):
    current = getattr(root, "zoom_factor", 1.0) or 1.0
    new_zoom = max(0.5, min(2.5, current * factor))
    if abs(new_zoom - current) < 0.01:
        return
    root.zoom_factor = new_zoom
    _apply_zoom(root)


def _set_zoom(root, value):
    current = getattr(root, "zoom_factor", 1.0) or 1.0
    new_zoom = max(0.5, min(2.5, value))
    if abs(new_zoom - current) < 0.01:
        return
    root.zoom_factor = new_zoom
    _apply_zoom(root)


def _refresh_connections(root):
    for conn in root.connections:
        conn.update_position()


def on_block_click(root, step_id, step_data, event):
    if root and getattr(root, "flowchart_data", None):
        step_data = root.flowchart_data.get("steps", {}).get(step_id, step_data or {})
    root.selected_step_id = step_id
    if getattr(root, "details_panel_widget", None):
        root.details_panel_widget.setVisible(True)
    root.details_panel['step_id'].setText(step_id)
    root.details_panel['description'].setPlainText(step_data.get('description', ''))
    
    files_list = root.details_panel['files']
    files_list.clear()
    files_list.addItems(step_data.get('filenames', []))

    imports_list = root.details_panel.get('imports')
    imports_list.clear()
    imports_list.addItems(step_data.get('files_to_import', []))
    
    children_list = root.details_panel['children']
    children_list.clear()
    children_list.addItems(_get_children(step_data))
    
    commands = step_data.get('command', [])
    root.details_panel['commands'].setPlainText('\n'.join(commands))
    
    for block in root.blocks.values():
        block.setProperty("selected", False)
        block.style().unpolish(block)
        block.style().polish(block)
        block.update()

    selected_block = root.blocks.get(step_id)
    if selected_block:
        selected_block.setProperty("selected", True)
        selected_block.style().unpolish(selected_block)
        selected_block.style().polish(selected_block)
        selected_block.update()


def on_block_moved(root, block):
    scale = getattr(root, "zoom_factor", 1.0) or 1.0
    if scale <= 0:
        return
    origin_x, origin_y = getattr(root, "_canvas_origin", (0.0, 0.0))
    center_x = (block.x() + (block.width() / 2.0)) / scale + origin_x
    center_y = (block.y() + (block.height() / 2.0)) / scale + origin_y
    root._layout_positions[block.step_id] = (center_x, center_y)
    _persist_layout_positions(root)
    _ensure_canvas_fits_graph(root)


def on_save_changes(root):
    if not root.selected_step_id:
        QMessageBox.warning(root, "No Selection", "Please select a step first.")
        return
    
    try:
        prev_flowchart = json.loads(json.dumps(root.flowchart_data)) if root.flowchart_data else {}
        prev_data = root.flowchart_data['steps'].get(root.selected_step_id, {})
        connection_meta = prev_data.get("connection_meta", {})
        updated_children = [
            root.details_panel['children'].item(i).text()
            for i in range(root.details_panel['children'].count())
        ]
        connection_meta = {
            child_id: meta
            for child_id, meta in connection_meta.items()
            if child_id in updated_children
        }
        updated_data = {
            'id': root.selected_step_id,
            'description': root.details_panel['description'].toPlainText(),
            'filenames': [
                root.details_panel['files'].item(i).text() 
                for i in range(root.details_panel['files'].count())
            ],
            'children': updated_children,
            'command': root.details_panel['commands'].toPlainText().split('\n'),
            'files_to_import': [
                root.details_panel['imports'].item(i).text()
                for i in range(root.details_panel['imports'].count())
            ],
            'connection_meta': connection_meta
        }
        
        print(root.code_editor_engine)

        root.flowchart_data['steps'][root.selected_step_id] = updated_data
        save_flowchart_to_file(root.flowchart_data)
        load_flowchart(root, root.flowchart_data)

        if root.code_editor_engine:
            root.code_editor_engine.add_changes(prev_flowchart, root.flowchart_data)
            update_generate_button(root)
        
        QMessageBox.information(root, "Success", "Changes saved! Connections updated.")
    except Exception as e:
        QMessageBox.critical(root, "Error", f"Failed to save: {e}")


def on_add_file(root):
    if not root.selected_step_id:
        QMessageBox.warning(root, "No Selection", "Please select a step first.")
        return
    filename, ok = QInputDialog.getText(root, "Add File", "Enter filename:")
    if ok and filename:
        root.details_panel['files'].addItem(filename)


def on_remove_file(root):
    files_list = root.details_panel['files']
    current_row = files_list.currentRow()
    if current_row >= 0:
        files_list.takeItem(current_row)
    else:
        QMessageBox.warning(root, "No Selection", "Please select a file to remove.")


def on_add_import(root):
    if not root.selected_step_id:
        QMessageBox.warning(root, "No Selection", "Please select a step first.")
        return
    filename, ok = QInputDialog.getText(root, "Add Import", "Enter file to import:")
    if ok and filename:
        root.details_panel['imports'].addItem(filename)


def on_remove_import(root):
    imports_list = root.details_panel['imports']
    current_row = imports_list.currentRow()
    if current_row >= 0:
        imports_list.takeItem(current_row)
    else:
        QMessageBox.warning(root, "No Selection", "Please select a file to remove.")


def on_add_child(root):
    if not root.selected_step_id:
        QMessageBox.warning(root, "No Selection", "Please select a step first.")
        return
    
    available_steps = [
        step_id for step_id in root.flowchart_data['steps'].keys()
        if step_id != root.selected_step_id
    ]
    
    if not available_steps:
        QMessageBox.warning(root, "No Steps", "No other steps available to connect.")
        return
    
    child_id, ok = QInputDialog.getItem(
        root, "Add Connection", "Select next step:", available_steps, 0, False
    )
    
    if ok and child_id:
        current_children = [
            root.details_panel['children'].item(i).text()
            for i in range(root.details_panel['children'].count())
        ]
        
        if child_id in current_children:
            QMessageBox.warning(root, "Duplicate", f"Already connected to {child_id}!")
            return
        
        root.details_panel['children'].addItem(child_id)


def on_remove_child(root):
    children_list = root.details_panel['children']
    current_row = children_list.currentRow()
    if current_row >= 0:
        children_list.takeItem(current_row)
    else:
        QMessageBox.warning(root, "No Selection", "Please select a connection to remove.")


def connect_blocks(root, from_id, to_id, from_dot_index, drop_pos):
    if not from_id or not to_id or from_id == to_id:
        return
    if not root.flowchart_data or "steps" not in root.flowchart_data:
        return
    if from_id not in root.flowchart_data["steps"]:
        return
    if to_id not in root.flowchart_data["steps"]:
        return
    step = root.flowchart_data["steps"][from_id]
    children = _get_children(step)
    if to_id in children:
        return
    children.append(to_id)
    _set_children(step, children)
    connection_meta = step.get("connection_meta", {})
    to_block = root.blocks.get(to_id)
    to_dot_index = None
    if to_block and drop_pos is not None:
        to_dot_index = to_block.nearest_dot_index(drop_pos)
    connection_meta[to_id] = {
        "from_dot": from_dot_index,
        "to_dot": to_dot_index
    }
    step["connection_meta"] = connection_meta
    save_flowchart_to_file(root.flowchart_data)
    load_flowchart(root, root.flowchart_data)
    root.selected_step_id = from_id
    on_block_click(root, from_id, root.flowchart_data["steps"][from_id], None)


def remove_connection(root, from_id, to_id):
    if not from_id or not to_id or from_id == to_id:
        return
    if not root.flowchart_data or "steps" not in root.flowchart_data:
        return
    step = root.flowchart_data["steps"].get(from_id)
    if not step:
        return
    children = _get_children(step)
    if to_id in children:
        children.remove(to_id)
        _set_children(step, children)
    if "connection_meta" in step and to_id in step["connection_meta"]:
        step["connection_meta"].pop(to_id, None)
    save_flowchart_to_file(root.flowchart_data)
    load_flowchart(root, root.flowchart_data)
    root.selected_step_id = from_id
    on_block_click(root, from_id, root.flowchart_data["steps"][from_id], None)


def on_add_step(root):
    step_id, ok = QInputDialog.getText(root, "Add Step", "Enter step ID (e.g., step5):")
    if not ok or not step_id:
        return
    
    if step_id in root.flowchart_data['steps']:
        QMessageBox.warning(root, "Duplicate ID", f"Step '{step_id}' already exists!")
        return
    
    new_step = {
        'id': step_id,
        'description': 'New step - edit description here',
        'filenames': [],
        'files_to_import': [],
        'command': [],
        'children': []
    }
    
    prev_flowchart = json.loads(json.dumps(root.flowchart_data)) if root.flowchart_data else {}

    root.flowchart_data['steps'][step_id] = new_step
    save_flowchart_to_file(root.flowchart_data)
    load_flowchart(root, root.flowchart_data)

    if root.code_editor_engine:
        root.code_editor_engine.add_changes(prev_flowchart, root.flowchart_data)
        update_generate_button(root)
    
    QMessageBox.information(root, "Success", f"Step '{step_id}' added!")


def on_delete_step(root):
    if not root.selected_step_id:
        QMessageBox.warning(root, "No Selection", "Please select a step to delete.")
        return
    
    step_id = root.selected_step_id
    
    reply = QMessageBox.question(
        root, "Confirm Delete", f"Delete step '{step_id}'?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    
    if reply == QMessageBox.StandardButton.No:
        return
    
    step_data = root.flowchart_data['steps'].get(step_id, {})
    prev_flowchart = json.loads(json.dumps(root.flowchart_data)) if root.flowchart_data else {}

    del root.flowchart_data['steps'][step_id]
    if step_id in getattr(root, "_layout_positions", {}):
        root._layout_positions.pop(step_id, None)
    if "layout_positions" in root.flowchart_data:
        root.flowchart_data["layout_positions"].pop(step_id, None)
    
    for step_data in root.flowchart_data['steps'].values():
        children = _get_children(step_data)
        if step_id in children:
            children.remove(step_id)
            _set_children(step_data, children)
        if step_id in step_data.get('connection_meta', {}):
            step_data['connection_meta'].pop(step_id, None)
    
    save_flowchart_to_file(root.flowchart_data)
    load_flowchart(root, root.flowchart_data)

    if root.code_editor_engine:
        root.code_editor_engine.add_changes(prev_flowchart, root.flowchart_data)
        update_generate_button(root)
    
    root.selected_step_id = None
    root.details_panel['step_id'].setText("No step selected")
    root.details_panel['description'].setPlainText("")
    root.details_panel['files'].clear()
    if root.details_panel.get('imports'):
        root.details_panel['imports'].clear()
    root.details_panel['children'].clear()
    root.details_panel['commands'].setPlainText("")
    
    QMessageBox.information(root, "Success", f"Step '{step_id}' deleted!")


def save_flowchart_to_file(flowchart_data):
    cache = load_cache()
    project_id = cache.get("current_project_id")
    
    if not project_id:
        raise Exception("No project ID found in cache")
    
    appdata_root = os.path.join(os.getenv("APPDATA", ""), "SVCA")
    flowchart_path = os.path.join(appdata_root, f"{project_id}.flowchart.json")
    
    with open(flowchart_path, 'w', encoding='utf-8') as f:
        json.dump(flowchart_data, f, indent=2)

class CodeGenerationWorker(QThread):
    """Worker thread for code generation."""
    finished = pyqtSignal(bool, str)  # success, message
    progress = pyqtSignal(str)
    
    def __init__(self, flowchart_dict, project_root):
        super().__init__()
        self.flowchart_dict = flowchart_dict
        self.project_root = project_root
    
    def run(self):
        """Run code generation in background thread."""
        try:
            from src.core.Flowchart import Flowchart
            from src.core.CodeGen import CodingAgent

            flowchart = Flowchart(name="", framework="", project_root=self.project_root)
            flowchart = flowchart.dictionary_to_flowchart(self.flowchart_dict)

            agent = CodingAgent(flowchart.project_root)

            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    agent.generate_project(self.flowchart_dict, progress=self._report_progress)
                    self.finished.emit(True, "Code generated successfully!")
                    return
                except Exception as e:
                    if not is_connection_error(e) or attempt >= max_retries:
                        raise
                    self.progress.emit(
                        f"Connection issue. Retrying in 3 seconds... ({attempt}/{max_retries})"
                    )
                    time.sleep(3)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"Code generation failed: {e}")

    def _report_progress(self, step_id: str, description: str) -> None:
        desc = description.strip() if description else ""
        if desc:
            self.progress.emit(f"Generating: {step_id} - {desc}")
        else:
            self.progress.emit(f"Generating: {step_id}")


class EditGenerationWorker(QThread):
    finished = pyqtSignal(bool, str, object, object)  # success, message, edits_text, edit_log
    progress = pyqtSignal(str)

    def __init__(self, code_editor_engine, flowchart_data):
        super().__init__()
        self.code_editor_engine = code_editor_engine
        self.flowchart_data = flowchart_data

    def run(self):
        try:
            edits_text, edit_log = self.code_editor_engine.generate_edit(
                flowchart_data=self.flowchart_data,
                progress=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(True, "", edits_text, edit_log)
        except Exception as e:
            self.finished.emit(False, str(e), "", [])


def _update_loading_message(loading, message: str) -> None:
    loading.set_message(message)


def _detect_code_generated(project_root: str) -> bool:
    if not project_root or not os.path.exists(project_root):
        return False
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith('.')
            and d not in ['__pycache__', 'node_modules', 'venv', 'env']
        ]
        for filename in filenames:
            if filename.startswith('.'):
                continue
            if filename.endswith('.json') or filename.endswith('.pyc'):
                continue
            return True
    return False


def _call_on_code_generated(root) -> bool:
    callback_found = False
    widget = root
    for level in range(10):
        if not widget:
            break
        if hasattr(widget, 'on_code_generated') and widget.on_code_generated:
            print(f"✓ Found callback on {type(widget).__name__} (level {level})")
            widget.on_code_generated()
            callback_found = True
            break
        widget = widget.parent()
    if not callback_found:
        print("⚠ Warning: on_code_generated callback not found!")
        print("   Code was generated successfully but cannot navigate automatically.")
    return callback_found


def _stop_worker(worker, timeout_ms: int = 2000) -> None:
    if not worker or not isinstance(worker, QThread):
        return
    if worker.isRunning():
        worker.requestInterruption()
        worker.wait(timeout_ms)
        if worker.isRunning():
            worker.terminate()
            worker.wait(1000)
            

def on_generate_code(root):
    """Generate code from flowchart."""
    if root.code_generated and root.code_editor_engine and root.code_editor_engine.has_changes():
        loading = LoadingScreen(root, "Generating edits...")
        loading.show()
        QApplication.processEvents()
        worker = EditGenerationWorker(root.code_editor_engine, root.flowchart_data)
        worker.progress.connect(partial(_update_loading_message, loading))
        worker.finished.connect(partial(_handle_edit_generation_finished, root, loading))
        worker.start()
        root.edit_worker = worker
        return
    
    cache = load_cache()
    project_id = cache.get("current_project_id")
    
    if not project_id:
        QMessageBox.warning(None, "Error", "No project loaded!")
        return
    
    appdata_root = os.path.join(os.getenv("APPDATA", ""), "SVCA")
    flowchart_path = os.path.join(appdata_root, f"{project_id}.flowchart.json")
    
    if not os.path.exists(flowchart_path):
        QMessageBox.warning(None, "Error", "Flowchart file not found!")
        return
    
    try:
        with open(flowchart_path, 'r', encoding='utf-8') as f:
            flowchart_dict = json.load(f)
    except Exception as e:
        QMessageBox.critical(None, "Error", f"Failed to load flowchart: {e}")
        return
    
    project_root = flowchart_dict.get('project_root', '')
    if not project_root:
        QMessageBox.critical(None, "Error", "Project root not found in flowchart data")
        return
    
    # ✅ Show loading screen IMMEDIATELY
    loading = LoadingScreen(root, "Generating code...")
    loading.show()
    QApplication.processEvents()  # Force immediate display
    
    # ✅ Create worker thread
    worker = CodeGenerationWorker(flowchart_dict, project_root)
    worker.progress.connect(partial(_update_loading_message, loading))
    
    # ✅ Connect completion signal
    worker.finished.connect(partial(_handle_code_generation_finished, root, loading))
    
    # ✅ Start generation in background
    worker.start()
    
    # Store worker reference so it doesn't get garbage collected
    root.worker = worker


def update_generate_button(root):
    if not hasattr(root, "generate_btn") or not root.generate_btn:
        return
    has_changes = bool(root.code_editor_engine and root.code_editor_engine.has_changes())
    if root.code_generated and not has_changes:
        root.generate_btn.setVisible(False)
    else:
        root.generate_btn.setVisible(True)
    if root.code_generated and has_changes:
        root.generate_btn.setText("Apply Edits")
        root.generate_btn.setToolTip("Generate edits from changes")
    else:
        root.generate_btn.setText("Generate Code")
        root.generate_btn.setToolTip("Generate code")
    if hasattr(root, "open_editor_btn") and root.open_editor_btn:
        root.open_editor_btn.setVisible(bool(root.code_generated))


def on_open_editor(root):
    if not root.code_generated:
        QMessageBox.information(root, "Not Ready", "Generate code first.")
        return
    _call_on_code_generated(root)



class CanvaWidget(QWidget):
    def __init__(self, on_back=None):
        super().__init__()
        self.setObjectName("CanvaWidget")
        self.on_code_generated = None  # ✅ Store callback
        self.on_back = on_back
        
        style_path = Path(__file__).resolve().parent.parent / "style" / "canva.qss"
        if style_path.exists():
            self.setStyleSheet(style_path.read_text(encoding="utf-8"))
        
        cache = load_cache()
        project_id = cache.get("current_project_id")
        flowchart_data = None
        
        if project_id:
            appdata_root = os.path.join(os.getenv("APPDATA", ""), "SVCA")
            flowchart_path = os.path.join(appdata_root, f"{project_id}.flowchart.json")
            
            if os.path.exists(flowchart_path):
                try:
                    with open(flowchart_path, "r", encoding="utf-8") as f:
                        flowchart_data = json.load(f)
                except Exception as e:
                    print(f"Error loading flowchart: {e}")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        canvas_widget = build_canva(flowchart_data, on_back=on_back)
        self.canvas_widget = canvas_widget  # ✅ Store reference
        layout.addWidget(canvas_widget)

    def reload_flowchart(self):
        cache = load_cache()
        project_id = cache.get("current_project_id")
        if not project_id:
            return
        appdata_root = os.path.join(os.getenv("APPDATA", ""), "SVCA")
        flowchart_path = os.path.join(appdata_root, f"{project_id}.flowchart.json")
        if not os.path.exists(flowchart_path):
            return
        try:
            with open(flowchart_path, "r", encoding="utf-8") as f:
                flowchart_data = json.load(f)
        except Exception:
            return
        if self.canvas_widget:
            self.canvas_widget.flowchart_data = flowchart_data
            load_flowchart(self.canvas_widget, flowchart_data)
    
    def showEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().showEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "canvas_widget") and self.canvas_widget:
            worker = getattr(self.canvas_widget, "worker", None)
            _stop_worker(worker)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = build_canva()
    window.show()
    sys.exit(app.exec())
