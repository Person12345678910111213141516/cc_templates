import json
import os
import sys
from typing import Optional, Dict, List
from enum import IntFlag, auto

from PyQt5 import QtCore, QtGui, QtWidgets
import logging


# -----------------------------
# Data Structures & Utilities
# -----------------------------


def rect_to_dict(x: float, y: float, w: float, h: float) -> Dict:
    return {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}


def dict_to_rect(d: Dict) -> QtCore.QRectF:
    return QtCore.QRectF(d["x"], d["y"], d["w"], d["h"])


# -----------------------------
# Graphics Items with composition-based signals (no multiple inheritance)
# -----------------------------
class RectItemSignals(QtCore.QObject):
    geometry_changed = QtCore.pyqtSignal(int)  # box_id


class RectItem(QtWidgets.QGraphicsRectItem):
    """QGraphicsRectItem that keeps (x,y) in item.pos() and (w,h) in rect(0,0,w,h).
    Emits geometry_changed via a composed QObject (RectItemSignals).

    New: Ctrl+Drag to resize from edges/corners. Hover shows size cursors.
    """

    class Edge(IntFlag):
        NONE = 0
        LEFT = auto()
        RIGHT = auto()
        TOP = auto()
        BOTTOM = auto()

    HANDLE_MARGIN = 10      # px, in item(local) coords
    MIN_SIZE = 1            # px

    def __init__(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        box_id: int,
        meta: Optional[Dict] = None,
    ):
        super().__init__(QtCore.QRectF(0, 0, w, h))
        self.setPos(x, y)
        self.box_id = box_id
        self.meta = meta or {
            "entity_name": "",
            "animation_name": "",
            "frame_number": 0,
        }
        self.signals = RectItemSignals()

        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._normal_pen = QtGui.QPen(QtGui.QColor(0, 170, 255), 2)
        self._hover_pen = QtGui.QPen(QtGui.QColor(255, 170, 0), 2, QtCore.Qt.DashLine)
        self._selected_pen = QtGui.QPen(QtGui.QColor(0, 255, 0), 2)
        self._brush = QtGui.QBrush(QtGui.QColor(0, 170, 255, 40))
        self.setPen(self._normal_pen)
        self.setBrush(self._brush)

        # --- resize state ---
        self._resizing = False
        self._resize_edges = RectItem.Edge.NONE
        self._press_pos_local = QtCore.QPointF()
        self._start_rect = QtCore.QRectF()
        self._start_pos = QtCore.QPointF()

    # ---------- Hover + cursors ----------
    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        self.setPen(self._hover_pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        self.unsetCursor()
        self.setPen(self._selected_pen if self.isSelected() else self._normal_pen)
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        edges = self._hit_test_handles(event.pos())
        self._apply_cursor_for_edges(edges)
        super().hoverMoveEvent(event)

    # ---------- Painting ----------
    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget=None,
    ):
        self.setPen(self._selected_pen if self.isSelected() else self._normal_pen)
        super().paint(painter, option, widget)

    # ---------- Selection/Move change -> signal ----------
    def itemChange(self, change, value):
        if change in (
            QtWidgets.QGraphicsItem.ItemSelectedHasChanged,
            QtWidgets.QGraphicsItem.ItemPositionHasChanged,
            QtWidgets.QGraphicsItem.ItemTransformHasChanged,
        ):
            self.signals.geometry_changed.emit(self.box_id)
        return super().itemChange(change, value)

    # ---------- Mouse for resizing ----------
    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            edges = self._hit_test_handles(event.pos())
            if edges != RectItem.Edge.NONE:
                # Begin resize
                self._resizing = True
                self._resize_edges = edges
                self._press_pos_local = event.pos()
                self._start_rect = QtCore.QRectF(self.rect())
                self._start_pos = QtCore.QPointF(self.pos())
                self._apply_cursor_for_edges(edges)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        if self._resizing:
            # delta in local coords (because event.pos() is local)
            dx = event.pos().x() - self._press_pos_local.x()
            dy = event.pos().y() - self._press_pos_local.y()

            new_x = self._start_pos.x()
            new_y = self._start_pos.y()
            new_w = self._start_rect.width()
            new_h = self._start_rect.height()

            # Horizontal edges
            if self._resize_edges & RectItem.Edge.LEFT:
                # dragging left edge changes x and width inversely
                new_w = max(self.MIN_SIZE, self._start_rect.width() - dx)
                # compute how much width changed to shift pos
                shift_x = (self._start_rect.width() - new_w)
                new_x = self._start_pos.x() + shift_x
            elif self._resize_edges & RectItem.Edge.RIGHT:
                new_w = max(self.MIN_SIZE, self._start_rect.width() + dx)

            # Vertical edges
            if self._resize_edges & RectItem.Edge.TOP:
                new_h = max(self.MIN_SIZE, self._start_rect.height() - dy)
                shift_y = (self._start_rect.height() - new_h)
                new_y = self._start_pos.y() + shift_y
            elif self._resize_edges & RectItem.Edge.BOTTOM:
                new_h = max(self.MIN_SIZE, self._start_rect.height() + dy)

            # Apply (keep local rect anchored at 0,0)
            self.setRect(0, 0, new_w, new_h)
            self.setPos(int(round(new_x)), int(round(new_y)))

            # Keep UI synced live
            self.signals.geometry_changed.emit(self.box_id)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        if self._resizing and event.button() == QtCore.Qt.LeftButton:
            self._resizing = False
            self._resize_edges = RectItem.Edge.NONE
            self.unsetCursor()
            # final sync
            self.signals.geometry_changed.emit(self.box_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---------- Helpers ----------
    def _hit_test_handles(self, p_local: QtCore.QPointF) -> "RectItem.Edge":
        """Return which edge(s) the point is 'near'. Corners are combinations.
        Uses a margin and allows slightly outside the rect (pen width, anti-aliasing)."""
        r = self.rect()
        x, y = p_local.x(), p_local.y()
        m = self.HANDLE_MARGIN

        edges = RectItem.Edge.NONE

        # near vertical band spanning the rect height ± margin
        if -m <= y <= r.height() + m:
            if abs(x - 0) <= m:
                edges |= RectItem.Edge.LEFT
            if abs(x - r.width()) <= m:
                edges |= RectItem.Edge.RIGHT

        # near horizontal band spanning the rect width ± margin
        if -m <= x <= r.width() + m:
            if abs(y - 0) <= m:
                edges |= RectItem.Edge.TOP
            if abs(y - r.height()) <= m:
                edges |= RectItem.Edge.BOTTOM

        return edges

    def _apply_cursor_for_edges(self, edges: "RectItem.Edge"):
        # Choose appropriate size cursor
        if edges in (RectItem.Edge.LEFT, RectItem.Edge.RIGHT):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        elif edges in (RectItem.Edge.TOP, RectItem.Edge.BOTTOM):
            self.setCursor(QtCore.Qt.SizeVerCursor)
        elif edges in (
            RectItem.Edge.TOP | RectItem.Edge.LEFT,
            RectItem.Edge.BOTTOM | RectItem.Edge.RIGHT,
        ):
            self.setCursor(QtCore.Qt.SizeFDiagCursor)  # ↘︎↖︎
        elif edges in (
            RectItem.Edge.TOP | RectItem.Edge.RIGHT,
            RectItem.Edge.BOTTOM | RectItem.Edge.LEFT,
        ):
            self.setCursor(QtCore.Qt.SizeBDiagCursor)  # ↗︎↙︎
        else:
            self.unsetCursor()

    def scene_rect(self) -> QtCore.QRectF:
        p = self.pos()
        r = self.rect()
        return QtCore.QRectF(p.x(), p.y(), r.width(), r.height())


# -----------------------------
# Graphics View for Image & Drawing
# -----------------------------
class SpriteView(QtWidgets.QGraphicsView):
    image_changed = QtCore.pyqtSignal()
    box_created = QtCore.pyqtSignal(RectItem)
    selection_changed = QtCore.pyqtSignal()
    path_dropped = QtCore.pyqtSignal(str)  # emits any dropped file path (.png or .json)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.BoundingRectViewportUpdate)
        self.setAcceptDrops(True)
        # Important: the QGraphicsView uses an internal viewport widget that actually receives the DnD events
        self.viewport().setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item: Optional[QtWidgets.QGraphicsPixmapItem] = None
        self._drawing = False
        self._start_pos = QtCore.QPointF()
        self._rubber_item: Optional[QtWidgets.QGraphicsRectItem] = None

        # Zoom support
        self._zoom = 1.0
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        self._scene.selectionChanged.connect(self.selection_changed)

    # ------------- Drag & Drop -------------
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                low = url.toLocalFile().lower()
                if low.endswith(".png") or low.endswith(".json"):
                    logging.info("[SpriteView] dragEnterEvent accept: %s", low)
                    event.acceptProposedAction()
                    return
        logging.info("[SpriteView] dragEnterEvent ignore")
        event.ignore()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                low = url.toLocalFile().lower()
                if low.endswith(".png") or low.endswith(".json"):
                    # keep accepting while dragging over the view
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent):
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            logging.info("[SpriteView] dropEvent path: %s", local)
            try:
                self.path_dropped.emit(local)
                event.acceptProposedAction()
            except Exception as ex:
                logging.exception("[SpriteView] path_dropped emit failed: %s", ex)
            break

    # ------------- Image Handling -------------
    def load_image(self, path: str):
        logging.info("[SpriteView] load_image: %s", path)
        pix = QtGui.QPixmap(path)
        if pix.isNull():
            logging.error("[SpriteView] load_image failed: %s", path)
            QtWidgets.QMessageBox.warning(
                self, "Load Error", "Failed to load image: " + path
            )
            return
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pix)
        self._pixmap_item.setZValue(-100)
        # Fix: use numbers to avoid type issues
        self._scene.setSceneRect(*pix.rect().getRect())
        self.resetTransform()
        self._zoom = 1.0
        self.image_changed.emit()
        logging.info("[SpriteView] image loaded: %dx%d", pix.width(), pix.height())

    def image_loaded(self) -> bool:
        return self._pixmap_item is not None

    # ------------- Mouse for Drawing -------------
    def start_draw_mode(self):
        QtWidgets.QToolTip.showText(
            QtGui.QCursor.pos(), "Hold Shift, then drag on the image to draw a box."
        )

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if (
            self.image_loaded()
            and event.button() == QtCore.Qt.LeftButton
            and (event.modifiers() & QtCore.Qt.ShiftModifier)
        ):
            self._drawing = True
            self._start_pos = self.mapToScene(event.pos())
            self._rubber_item = self._scene.addRect(
                QtCore.QRectF(self._start_pos, self._start_pos),
                QtGui.QPen(QtGui.QColor(255, 0, 0), 1, QtCore.Qt.DashLine),
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self._drawing and self._rubber_item is not None:
            curr = self.mapToScene(event.pos())
            rect = QtCore.QRectF(self._start_pos, curr).normalized()
            self._rubber_item.setRect(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if self._drawing and event.button() == QtCore.Qt.LeftButton:
            self._drawing = False
            rect = self._rubber_item.rect() if self._rubber_item else QtCore.QRectF()
            if self._rubber_item:
                self._scene.removeItem(self._rubber_item)
                self._rubber_item = None

            if rect.width() >= 1 and rect.height() >= 1:
                img_rect = QtCore.QRectF(self._pixmap_item.pixmap().rect())
                rect = rect.intersected(img_rect)
                item = RectItem(
                    rect.x(), rect.y(), rect.width(), rect.height(), box_id=-1
                )
                self.box_created.emit(item)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------- Zoom -------------
    def wheelEvent(self, event: QtGui.QWheelEvent):
        if not self.image_loaded():
            return super().wheelEvent(event)
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else 1 / 1.15
        self._zoom *= factor
        self.scale(factor, factor)

    # ------------- Add/Remove Boxes -------------
    def add_box_item(self, item: RectItem):
        self._scene.addItem(item)
        item.setZValue(10)

    def remove_selected(self) -> List[int]:
        removed_ids = []
        for it in list(self._scene.selectedItems()):
            if isinstance(it, RectItem):
                removed_ids.append(it.box_id)
                self._scene.removeItem(it)
        return removed_ids

    def all_rect_items(self) -> List[RectItem]:
        return [it for it in self._scene.items() if isinstance(it, RectItem)]


# -----------------------------
# Metadata Panel (Dock)
# -----------------------------
class MetadataPanel(QtWidgets.QWidget):
    """Edits either a single box or applies *only changed fields* to all selections.
    Numeric fields are QLineEdit+validators so they can be blank for mixed values."""

    # Emits only the fields that actually changed, e.g. {
    #   'entity_name': 'orc', 'rect': {'x': 12, 'h': 64}, 'frame_number': 3
    # }
    fields_changed = QtCore.pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selection_count = 0
        self._touched: set = set()  # which fields were edited by the user

        # Banner shows multi-edit state
        self.banner = QtWidgets.QLabel("")
        self.banner.setStyleSheet("color:#2b6;font-weight:600;")

        # Text fields
        self.entity_edit = QtWidgets.QLineEdit()
        self._wire_text(self.entity_edit, "entity_name")
        self.anim_edit = QtWidgets.QLineEdit()
        self._wire_text(self.anim_edit, "animation_name")

        # Numeric as QLineEdit so we can display blank on mixed
        def int_edit(name, minv=0, maxv=1_000_000):
            e = QtWidgets.QLineEdit()
            e.setValidator(QtGui.QIntValidator(minv, maxv, e))
            self._wire_text(e, name)
            return e

        self.frame_edit = int_edit("frame_number", 0, 10000)
        self.x_edit = int_edit("x")
        self.y_edit = int_edit("y")
        self.w_edit = int_edit("w", 1)
        self.h_edit = int_edit("h", 1)

        form = QtWidgets.QFormLayout()
        form.addRow(self.banner)
        form.addRow("Entity Name", self.entity_edit)
        form.addRow("Animation Name", self.anim_edit)
        form.addRow("Animation Frame #", self.frame_edit)
        form.addRow(QtWidgets.QLabel(""))
        form.addRow("X", self.x_edit)
        form.addRow("Y", self.y_edit)
        form.addRow("Width", self.w_edit)
        form.addRow("Height", self.h_edit)

        wrap = QtWidgets.QWidget()
        wrap.setLayout(form)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(wrap)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(scroll)

    # ---- helpers ----
    def _wire_text(self, widget: QtWidgets.QLineEdit, field_name: str):
        # mark as touched on any edit; emit on editingFinished with only this field
        def _mark(_):
            self._touched.add(field_name)

        def _emit():
            if field_name not in self._touched:
                return
            payload = {}
            if field_name in {
                "entity_name",
                "animation_name",
                "frame_number",
            }:
                if field_name == "frame_number":
                    txt = widget.text().strip()
                    if txt != "":
                        payload["frame_number"] = int(txt)
                else:
                    payload[field_name] = widget.text().strip()
            else:
                # rect field
                txt = widget.text().strip()
                if txt != "":
                    payload["rect"] = {field_name: int(txt)}
            if payload:
                self.fields_changed.emit(payload)
            # keep touched so successive edits still emit; clear on set_from_values

        widget.textEdited.connect(_mark)
        widget.editingFinished.connect(_emit)

    def set_selection_count(self, n: int):
        self._selection_count = n
        self.banner.setText(f"Editing {n} selected" if n > 1 else "")

    def set_from_values(self, meta: Dict, rect: Dict, multi: bool):
        """Set widget contents from possibly-partial values.
        Any key missing or set to None is shown as blank.
        When multi=True and a value is None, placeholder '(multiple)' is shown."""
        # prevent feedback loops
        edits: List[QtWidgets.QLineEdit] = [
            self.entity_edit,
            self.anim_edit,
            self.frame_edit,
            self.x_edit,
            self.y_edit,
            self.w_edit,
            self.h_edit,
        ]
        for w in edits:
            w.blockSignals(True)

        # text helpers
        def set_or_blank(edit: QtWidgets.QLineEdit, value):
            if value is None:
                edit.clear()
                edit.setPlaceholderText("(multiple)" if multi else "")
            else:
                edit.setText(str(value))
                edit.setPlaceholderText("")

        set_or_blank(self.entity_edit, meta.get("entity_name"))
        set_or_blank(self.anim_edit, meta.get("animation_name"))
        set_or_blank(self.frame_edit, meta.get("frame_number"))
        set_or_blank(self.x_edit, rect.get("x"))
        set_or_blank(self.y_edit, rect.get("y"))
        set_or_blank(self.w_edit, rect.get("w"))
        set_or_blank(self.h_edit, rect.get("h"))
        for w in edits:
            w.blockSignals(False)
        self._touched.clear()


# -----------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sprite Sheet Metadata Editor")
        self.resize(1320, 840)
        self.setAcceptDrops(True)

        self.view = SpriteView()
        self.view.image_changed.connect(self.on_image_changed)
        self.view.box_created.connect(self.on_box_created)
        self.view.selection_changed.connect(self.sync_selection_from_scene)
        self.view.path_dropped.connect(self.on_path_dropped)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list_widget.currentRowChanged.connect(self.on_list_selection_changed)
        self.list_widget.itemSelectionChanged.connect(
            self.on_list_items_selection_changed
        )
        self.list_widget.itemDoubleClicked.connect(self.focus_selected_box)

        self.add_btn = QtWidgets.QPushButton("+ New Box")
        self.add_btn.setToolTip("Add a new 64x64 box at (0,0)")
        self.add_btn.clicked.connect(self.add_new_box)

        self.del_btn = QtWidgets.QPushButton("Delete Selected")
        self.del_btn.clicked.connect(self.delete_selected_box)

        # Batch tools
        self.distrib_h_btn = QtWidgets.QPushButton("Distribute H")
        self.distrib_h_btn.setToolTip("Evenly distribute left edges horizontally")
        self.distrib_h_btn.clicked.connect(self.distribute_h)
        self.distrib_v_btn = QtWidgets.QPushButton("Distribute V")
        self.distrib_v_btn.setToolTip("Evenly distribute top edges vertically")
        self.distrib_v_btn.clicked.connect(self.distribute_v)

        side = QtWidgets.QWidget()
        side_lay = QtWidgets.QVBoxLayout(side)
        side_lay.addWidget(QtWidgets.QLabel("Boxes"))
        side_lay.addWidget(self.list_widget, 1)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.del_btn)
        side_lay.addLayout(btn_row)
        tool_row = QtWidgets.QHBoxLayout()
        tool_row.addWidget(self.distrib_h_btn)
        tool_row.addWidget(self.distrib_v_btn)
        side_lay.addLayout(tool_row)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([1100, 400])
        self.setCentralWidget(splitter)

        self.meta_panel = MetadataPanel()
        self.meta_panel.fields_changed.connect(self.on_meta_fields_changed)
        self.meta_dock = QtWidgets.QDockWidget("Metadata", self)
        self.meta_dock.setWidget(self.meta_panel)
        self.meta_dock.setAllowedAreas(
            QtCore.Qt.RightDockWidgetArea | QtCore.Qt.LeftDockWidgetArea
        )
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.meta_dock)

        self.statusBar().showMessage(
            "Drag & drop a PNG or JSON anywhere. Shift+Drag to draw a rectangle, or click '+ New Box'."
        )

        self.image_path: Optional[str] = None
        self.box_counter = 0
        self.box_index: Dict[int, RectItem] = {}

        self._build_menus()
        QtWidgets.QShortcut(
            QtGui.QKeySequence.Delete, self, activated=self.delete_selected_box
        )
        QtWidgets.QShortcut(QtGui.QKeySequence("N"), self, activated=self.add_new_box)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".png"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent):
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local.lower().endswith(".png"):
                self.view.load_image(local)
                self.image_path = local
                break

    def _build_menus(self):
        m = self.menuBar()
        file_menu = m.addMenu("File")

        a_open_img = file_menu.addAction("Open Image…")
        a_open_img.triggered.connect(self.open_image)
        a_open_img.setShortcut(QtGui.QKeySequence("Ctrl+O"))

        a_load_json = file_menu.addAction("Load Metadata JSON…")
        a_load_json.triggered.connect(self.load_metadata)
        a_load_json.setShortcut(QtGui.QKeySequence("Ctrl+L"))

        a_save_json = file_menu.addAction("Save Metadata JSON…")
        a_save_json.triggered.connect(self.save_metadata)
        a_save_json.setShortcut(QtGui.QKeySequence("Ctrl+S"))

        file_menu.addSeparator()
        a_quit = file_menu.addAction("Quit")
        a_quit.triggered.connect(self.close)

        help_menu = m.addMenu("Help")
        a_about = help_menu.addAction("About")
        a_about.triggered.connect(self.show_about)

        toolbar = self.addToolBar("Main")

        act_new_box = QtWidgets.QAction("New Box", self)
        act_new_box.triggered.connect(self.add_new_box)
        toolbar.addAction(act_new_box)

        act_draw_hint = QtWidgets.QAction("Draw (Shift+Drag)", self)
        act_draw_hint.triggered.connect(self.view.start_draw_mode)
        toolbar.addAction(act_draw_hint)

        toolbar.addSeparator()

        act_dh = QtWidgets.QAction("Distribute H", self)
        act_dh.setToolTip("Evenly distribute left edges of selected boxes")
        act_dh.triggered.connect(self.distribute_h)
        toolbar.addAction(act_dh)

        act_dv = QtWidgets.QAction("Distribute V", self)
        act_dv.setToolTip("Evenly distribute top edges of selected boxes")
        act_dv.triggered.connect(self.distribute_v)
        toolbar.addAction(act_dv)

    def show_about(self):
        msg = (
            "Sprite Sheet Metadata Editor "
            "• Drag & drop a PNG onto the window or use File → Open Image.  "
            "• Hold Shift and drag with left mouse to draw a rectangle (or click '+ New Box').  "
            "• Select a box to edit its metadata and coordinates in the Metadata dock.  "
            "• Press Delete to remove selected.  "
            "• Load/Save JSON via File menu."
        )
        QtWidgets.QMessageBox.information(self, "About", msg)

    def on_image_changed(self):
        for it in self.view.all_rect_items():
            self.view.scene().removeItem(it)
        self.list_widget.clear()
        self.box_index.clear()
        self.box_counter = 0

    def open_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open PNG", "", "PNG Images (*.png)"
        )
        if path:
            self.open_image_path(path)

    def open_image_path(self, path: str):
        if not path:
            return
        logging.info("[MainWindow] open_image_path: %s", path)
        self.view.load_image(path)
        self.image_path = path

    def add_new_box(self):
        if not self.view.image_loaded():
            QtWidgets.QMessageBox.information(
                self, "No Image", "Load or drop a PNG first."
            )
            return
        item = RectItem(0, 0, 64, 64, box_id=self.box_counter)
        self.box_counter += 1
        self.view.add_box_item(item)
        self.box_index[item.box_id] = item
        self._add_list_item(item)
        self.select_box_in_list(item.box_id)
        # ensure scene/list selection sync and panel reflects the single selection
        self.on_list_items_selection_changed()
        item.signals.geometry_changed.connect(self._on_rect_geom_changed)

    def _on_rect_geom_changed(self, box_id: int):
        ri = self.box_index.get(box_id)
        if not ri:
            return
        self._refresh_list_item(ri.box_id)
        self._update_meta_panel_from_selected()

    def on_box_created(self, item: RectItem):
        item.box_id = self.box_counter
        self.box_counter += 1
        self.view.add_box_item(item)
        self.box_index[item.box_id] = item
        self._add_list_item(item)
        self.select_box_in_list(item.box_id)
        self.on_list_items_selection_changed()
        item.signals.geometry_changed.connect(self._on_rect_geom_changed)

    def _add_list_item(self, rect_item: RectItem):
        lw_item = QtWidgets.QListWidgetItem(self._list_label(rect_item))
        lw_item.setData(QtCore.Qt.UserRole, rect_item.box_id)
        self.list_widget.addItem(lw_item)

    def _refresh_list_item(self, box_id: int):
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(QtCore.Qt.UserRole) == box_id:
                it.setText(self._list_label(self.box_index[box_id]))
                break

    def _list_label(self, rect_item: RectItem) -> str:
        r = rect_item.scene_rect().toRect()
        meta = rect_item.meta
        return (
            f"#{rect_item.box_id}: {meta.get('entity_name', '')} / {meta.get('animation_name', '')} "
            f"[frame {meta.get('frame_number', 0)}] -> ({r.x()},{r.y()},{r.width()}x{r.height()})"
        )

    def select_box_in_list(self, box_id: int):
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(QtCore.Qt.UserRole) == box_id:
                self.list_widget.setCurrentRow(i)
                break

    def get_selected_ids(self) -> List[int]:
        ids = []
        for it in self.list_widget.selectedItems():
            ids.append(it.data(QtCore.Qt.UserRole))
        return ids

    def get_selected_rect_items(self) -> List[RectItem]:
        return [
            self.box_index[i] for i in self.get_selected_ids() if i in self.box_index
        ]

    def get_selected_rect_item(self) -> Optional[RectItem]:
        items = self.get_selected_rect_items()
        return items[0] if items else None

    # ---- Batch arrange tools ----
    def distribute_h(self):
        items = self.get_selected_rect_items()
        if len(items) < 3:
            return
        items.sort(key=lambda ri: ri.pos().x())
        lefts = [ri.pos().x() for ri in items]
        first, last = lefts[0], lefts[-1]
        if last == first:
            step = 0
        else:
            step = (last - first) / (len(items) - 1)
        for i, ri in enumerate(items):
            ri.setPos(int(round(first + i * step)), int(ri.pos().y()))
            self._refresh_list_item(ri.box_id)
        self._update_meta_panel_from_selected()

    def distribute_v(self):
        items = self.get_selected_rect_items()
        if len(items) < 3:
            return
        items.sort(key=lambda ri: ri.pos().y())
        tops = [ri.pos().y() for ri in items]
        first, last = tops[0], tops[-1]
        if last == first:
            step = 0
        else:
            step = (last - first) / (len(items) - 1)
        for i, ri in enumerate(items):
            ri.setPos(int(ri.pos().x()), int(round(first + i * step)))
            self._refresh_list_item(ri.box_id)
        self._update_meta_panel_from_selected()

    def sync_selection_from_scene(self):
        selected_ids = [
            it.box_id
            for it in self.view._scene.selectedItems()
            if isinstance(it, RectItem)
        ]
        # Sync list selection to match scene selection
        self.list_widget.blockSignals(True)
        self.list_widget.clearSelection()
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(QtCore.Qt.UserRole) in selected_ids:
                it.setSelected(True)
        self.list_widget.blockSignals(False)
        # Update metadata panel with common values only
        self._update_meta_panel_from_selected()

    def on_list_selection_changed(self, idx: int):
        # Kept for compatibility with single selection changes
        self.on_list_items_selection_changed()

    def on_list_items_selection_changed(self):
        # Update scene selection from list selection
        selected_ids = self.get_selected_ids()
        for rect_item in self.view.all_rect_items():
            rect_item.setSelected(rect_item.box_id in selected_ids)
        # Update metadata panel with common values only
        self._update_meta_panel_from_selected()

    def _common_or_none(self, vals: List):
        vals = list(vals)
        if not vals:
            return None
        first = vals[0]
        for v in vals[1:]:
            if v != first:
                return None
        return first

    def _update_meta_panel_from_selected(self):
        items = self.get_selected_rect_items()
        n = len(items)
        if n == 0:
            self.meta_panel.set_selection_count(0)
            self.meta_panel.set_from_values({}, {}, multi=False)
            return
        self.meta_panel.set_selection_count(n)
        metas = [ri.meta for ri in items]
        rects = [ri.scene_rect() for ri in items]
        meta_values = {
            "entity_name": self._common_or_none(
                [m.get("entity_name", "") for m in metas]
            ),
            "animation_name": self._common_or_none(
                [m.get("animation_name", "") for m in metas]
            ),
            "frame_number": self._common_or_none(
                [int(m.get("frame_number", 0)) for m in metas]
            ),
        }
        rect_values = {
            "x": self._common_or_none([int(r.x()) for r in rects]),
            "y": self._common_or_none([int(r.y()) for r in rects]),
            "w": self._common_or_none([int(r.width()) for r in rects]),
            "h": self._common_or_none([int(r.height()) for r in rects]),
        }
        self.meta_panel.set_from_values(meta_values, rect_values, multi=(n > 1))

    def focus_selected_box(self):
        ri = self.get_selected_rect_item()
        if ri:
            self.view.centerOn(ri)
            self._update_meta_panel_from_selected()
            self.meta_dock.raise_()

    def on_meta_fields_changed(self, changes: Dict):
        # Apply *only* changed fields to the current selection
        items = self.get_selected_rect_items()
        if not items:
            return
        # Metadata keys
        if "entity_name" in changes:
            for ri in items:
                ri.meta["entity_name"] = changes["entity_name"]
        if "animation_name" in changes:
            for ri in items:
                ri.meta["animation_name"] = changes["animation_name"]
        if "frame_number" in changes:
            for ri in items:
                ri.meta["frame_number"] = int(
                    changes["frame_number"]
                )
        # Rect keys
        rect = changes.get("rect", {})
        for ri in items:
            x = int(ri.pos().x())
            y = int(ri.pos().y())
            w = int(ri.rect().width())
            h = int(ri.rect().height())
            if "x" in rect:
                x = int(rect["x"])
            if "y" in rect:
                y = int(rect["y"])
            if "w" in rect:
                w = int(rect["w"])
            if "h" in rect:
                h = int(rect["h"])
            ri.setRect(0, 0, w, h)
            ri.setPos(x, y)
        for ri in items:
            self._refresh_list_item(ri.box_id)
        # Refresh panel to reflect new common values
        self._update_meta_panel_from_selected()

    def delete_selected_box(self):
        selected_ids = self.get_selected_ids()
        if not selected_ids:
            return
        confirm = (
            f"Delete {len(selected_ids)} box(es)?"
            if len(selected_ids) > 1
            else f"Delete box #{selected_ids[0]}?"
        )
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete Box(es)",
            confirm,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        for i in reversed(range(self.list_widget.count())):
            it = self.list_widget.item(i)
            if it.data(QtCore.Qt.UserRole) in selected_ids:
                box_id = it.data(QtCore.Qt.UserRole)
                rect_item = self.box_index.pop(box_id, None)
                if rect_item:
                    self.view._scene.removeItem(rect_item)
                self.list_widget.takeItem(i)
        self.meta_panel.set_selection_count(0)
        self.meta_panel.set_from_values({}, {}, multi=False)

    def save_metadata(self):
        if not self.view.image_loaded():
            QtWidgets.QMessageBox.information(
                self, "Nothing to Save", "Load an image and create boxes first."
            )
            return
        default_name = "metadata.json"
        if self.image_path:
            base = os.path.splitext(os.path.basename(self.image_path))[0]
            default_name = f"{base}_metadata.json"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Metadata JSON", default_name, "JSON (*.json)"
        )
        if not path:
            return

        pix = self.view._pixmap_item.pixmap()
        data = {
            "image_path": self.image_path or "",
            "image_size": {"w": pix.width(), "h": pix.height()},
            "boxes": [],
        }
        for it in sorted(self.view.all_rect_items(), key=lambda it: it.box_id):
            r = it.scene_rect()
            data["boxes"].append(
                {
                    "id": it.box_id,
                    "rect": rect_to_dict(r.x(), r.y(), r.width(), r.height()),
                    **it.meta,
                }
            )
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as ex:
            QtWidgets.QMessageBox.warning(
                self, "Save Error", "Failed to save JSON: " + str(ex)
            )
            return
        self.statusBar().showMessage("Saved metadata -> " + path, 5000)

    def load_metadata(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Metadata JSON", "", "JSON (*.json)"
        )
        if not path:
            return
        self.load_metadata_path(path)

    def load_metadata_path(self, path: str):
        if not path:
            return
        logging.info("[MainWindow] load_metadata_path: %s", path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as ex:
            logging.exception("[MainWindow] load_metadata_path failed")
            QtWidgets.QMessageBox.warning(
                self, "Load Error", "Failed to read JSON: " + str(ex)
            )
            return

        img_path = data.get("image_path") or ""
        if img_path and os.path.exists(img_path):
            self.view.load_image(img_path)
            self.image_path = img_path
        elif not self.view.image_loaded():
            QtWidgets.QMessageBox.information(
                self,
                "Image Required",
                "The metadata file does not reference a valid image path. Please open the PNG first, then load the metadata again.",
            )
            return

        for it in self.view.all_rect_items():
            self.view._scene.removeItem(it)
        self.list_widget.clear()
        self.box_index.clear()
        self.box_counter = 0

        for b in data.get("boxes", []):
            r = b.get("rect", {"x": 0, "y": 0, "w": 1, "h": 1})
            meta = {
                "entity_name": b.get("entity_name", ""),
                "animation_name": b.get("animation_name", ""),
                "frame_number": int(b.get("frame_number", 0)),
            }
            box_id = int(b.get("id", self.box_counter))
            self.box_counter = max(self.box_counter, box_id + 1)
            item = RectItem(r["x"], r["y"], r["w"], r["h"], box_id=box_id, meta=meta)
            self.view.add_box_item(item)
            self.box_index[item.box_id] = item
            self._add_list_item(item)
            item.signals.geometry_changed.connect(self._on_rect_geom_changed)

        self.statusBar().showMessage("Loaded metadata from " + path, 5000)
        logging.info("[MainWindow] loaded %d boxes", len(self.box_index))
        return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as ex:
            QtWidgets.QMessageBox.warning(
                self, "Load Error", "Failed to read JSON: " + str(ex)
            )
            return

        img_path = data.get("image_path") or ""
        if img_path and os.path.exists(img_path):
            self.view.load_image(img_path)
            self.image_path = img_path
        elif not self.view.image_loaded():
            QtWidgets.QMessageBox.information(
                self,
                "Image Required",
                "The metadata file does not reference a valid image path. Please open the PNG first, then load the metadata again.",
            )
            return

        for it in self.view.all_rect_items():
            self.view._scene.removeItem(it)
        self.list_widget.clear()
        self.box_index.clear()
        self.box_counter = 0

        for b in data.get("boxes", []):
            r = b.get("rect", {"x": 0, "y": 0, "w": 1, "h": 1})
            meta = {
                "entity_name": b.get("entity_name", ""),
                "animation_name": b.get("animation_name", ""),
                "frame_number": int(b.get("frame_number", 0)),
            }
            box_id = int(b.get("id", self.box_counter))
            self.box_counter = max(self.box_counter, box_id + 1)
            item = RectItem(r["x"], r["y"], r["w"], r["h"], box_id=box_id, meta=meta)
            self.view.add_box_item(item)
            self.box_index[item.box_id] = item
            self._add_list_item(item)
            item.signals.geometry_changed.connect(self._on_rect_geom_changed)

        self.statusBar().showMessage("Loaded metadata from " + path, 5000)

    def on_path_dropped(self, path: str):
        logging.info("[MainWindow] on_path_dropped: %s", path)
        low = path.lower()
        if low.endswith(".json"):
            self.load_metadata_path(path)
        elif low.endswith(".png"):
            self.open_image_path(path)
        else:
            QtWidgets.QMessageBox.information(
                self, "Unsupported File", "Drop a .png or .json file."
            )


def _configure_logging(ns):
    # Determine level: flag > -v > env > default INFO
    if ns.log_level:
        level_name = ns.log_level
    elif ns.verbose >= 2:
        level_name = "DEBUG"
    elif ns.verbose == 1:
        level_name = "INFO"
    else:
        level_name = os.environ.get("LOGLEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="[%(levelname)s] %(message)s",
    )
    logging.debug("Resolved log level: %s", level_name)


def main(argv=None):
    import argparse
    from pathlib import Path
    from PyQt5 import QtWidgets

    parser = argparse.ArgumentParser(
        prog="sprite-meta-editor",
        description="Sprite Sheet Metadata Editor (Qt). Open a PNG and/or a JSON metadata file."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional positional paths: an image (.png) and/or a metadata file (.json). "
             "If both are given, order doesn't matter."
    )
    parser.add_argument(
        "-i", "--image",
        type=Path,
        help="Path to a sprite sheet image (.png)."
    )
    parser.add_argument(
        "-m", "--metadata",
        type=Path,
        help="Path to a sprite metadata file (.json)."
    )
    parser.add_argument(
        "-l", "--log-level",
        dest="log_level",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
        help="Logging level (overrides LOGLEVEL env)."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v=INFO, -vv=DEBUG). Ignored if --log-level is provided."
    )
    parser.add_argument(
        "--version",
        action="version",
        version="Sprite Sheet Metadata Editor 1.0.0"
    )
    ns =  parser.parse_args(argv)

    _configure_logging(ns)
    logging.info("Starting Sprite Sheet Metadata Editor")

    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName("SpriteTools")
    app.setApplicationName("Sprite Sheet Metadata Editor")

    w = MainWindow()

    # Determine image_path and metadata_path with the following priority:
    # 1) Explicit flags (--image/--metadata)
    # 2) Positional paths (by file extension)
    image_path = ns.image
    metadata_path = ns.metadata

    if ns.paths:
        # Infer from positional paths (extension-based)
        png = next((Path(p) for p in ns.paths if str(p).lower().endswith(".png")), None)
        jsn = next((Path(p) for p in ns.paths if str(p).lower().endswith(".json")), None)
        image_path = image_path or png
        metadata_path = metadata_path or jsn

    # Only open existing paths; warn otherwise.
    if image_path:
        if Path(image_path).exists():
            logging.info("Opening image: %s", image_path)
            w.open_image_path(str(image_path))
        else:
            logging.warning("Image path does not exist: %s", image_path)

    if metadata_path:
        if Path(metadata_path).exists():
            logging.info("Loading metadata: %s", metadata_path)
            w.load_metadata_path(str(metadata_path))
        else:
            logging.warning("Metadata path does not exist: %s", metadata_path)

    # If the user passed paths that exist but were neither .png nor .json, log what we saw.
    if ns.paths:
        existing = [str(p) for p in ns.paths if Path(p).exists()]
        if existing:
            logging.debug("Positional args (existing paths): %s", existing)

    w.resize(1500, 950)
    w.show()

    # Qt5 uses exec_(), Qt6 uses exec()
    exec_fn = getattr(app, "exec", None) or getattr(app, "exec_", None)
    sys.exit(exec_fn())


if __name__ == "__main__":
    main()
