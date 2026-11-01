# ui_components.py
import re
from PySide6.QtWidgets import (QHeaderView, QStyleOptionButton, QApplication,
                               QStyle, QStyledItemDelegate, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel,
                               QLineEdit, QComboBox, QSizePolicy, QStylePainter,
                               QStyleOptionComboBox)
from PySide6.QtCore import (Qt, QSortFilterProxyModel, QPoint, QRect, QEvent,
                            QItemSelection, QItemSelectionModel, QModelIndex, Signal,
                            QTimer)
from PySide6.QtGui import QColor, QPainter, QPolygon, QPen, QPainterPath

# ★ 从 ui_styles 引入统一颜色，避免重复定义和色彩漂移
from ui_styles import (
    TOGGLE_GREEN,
    BG_HOVER,
    TEXT_DARK,
    DANGER_RED,
    ERROR_BG,
    ERROR_BG_SELECTED
)

# ================= 统一默认样式常量（可被子页面传参覆盖） =================
CHECK_BG_COLOR = TOGGLE_GREEN  # 勾选框默认背景
CHECK_MARK_COLOR = "#FFFFFF"
CHECK_BORDER_COLOR = "#DCDCDC"
CHECK_BOX_SIZE = 16
CHECK_BOX_RADIUS = 4

HEADER_BG_COLOR = BG_HOVER
HEADER_FILTERED_BG_COLOR = "#FFF3E0"
HEADER_TRIANGLE_COLOR = "#666666"
HEADER_TRIANGLE_ACTIVE_COLOR = DANGER_RED

ROW_SELECTED_BG = BG_HOVER
ROW_HOVER_BG = BG_HOVER


# ================= 统一勾选框绘制工具 =================
def draw_checkbox(painter, rect, checked,
                  size=CHECK_BOX_SIZE,
                  radius=CHECK_BOX_RADIUS,
                  bg_color=CHECK_BG_COLOR,
                  mark_color=CHECK_MARK_COLOR,
                  border_color=CHECK_BORDER_COLOR,
                  border_width=1,
                  mark_width=2):
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)

    box_x = rect.center().x() - size // 2
    box_y = rect.center().y() - size // 2
    box_rect = QRect(box_x, box_y, size, size)

    if checked:
        painter.setBrush(QColor(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(box_rect, radius, radius)

        pen = QPen(QColor(mark_color))
        pen.setWidth(mark_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        s = size / 16.0
        p1 = QPoint(box_rect.left() + int(4 * s), box_rect.top() + int(8 * s))
        p2 = QPoint(box_rect.left() + int(7 * s), box_rect.top() + int(11 * s))
        p3 = QPoint(box_rect.left() + int(12 * s), box_rect.top() + int(5 * s))
        path = QPainterPath(p1)
        path.lineTo(p2)
        path.lineTo(p3)
        painter.drawPath(path)
    else:
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor(border_color), border_width))
        painter.drawRoundedRect(box_rect, radius, radius)

    painter.restore()


# ================= 统一三角箭头绘制工具 =================
def draw_arrow(painter, rect, color="#999999"):
    x = rect.right() - 16
    y = rect.center().y() - 2
    points = [QPoint(x, y), QPoint(x + 8, y), QPoint(x + 4, y + 5)]
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawPolygon(QPolygon(points))


# ================= 通用校验函数 =================
_ALNUM_PATTERN = re.compile(r'[A-Za-z0-9]+')


def is_alnum_only(text: str) -> bool:
    text = (text or "").strip()
    return (not text) or bool(_ALNUM_PATTERN.fullmatch(text))


# ================= 通用正则校验委托 =================
class PatternCellDelegate(QStyledItemDelegate):
    INVALID_BG = QColor(ERROR_BG)
    INVALID_BG_SELECTED = QColor(ERROR_BG_SELECTED)
    INVALID_FG = QColor(DANGER_RED)
    BORDER_COLOR = QColor("#E9ECEF")
    SELECT_BORDER = QColor(TOGGLE_GREEN)

    def __init__(self, pattern=_ALNUM_PATTERN, parent=None):
        super().__init__(parent)
        self.pattern = pattern if hasattr(pattern, 'fullmatch') else re.compile(pattern)

    def is_valid(self, text: str) -> bool:
        text = (text or "").strip()
        return (not text) or bool(self.pattern.fullmatch(text))

    def paint(self, painter, option, index):
        text = index.data(Qt.DisplayRole) or ""

        if self.is_valid(text):
            super().paint(painter, option, index)
        else:
            painter.save()

            if option.state & QStyle.State_Selected:
                painter.fillRect(option.rect.adjusted(0, 0, 0, -1), self.INVALID_BG_SELECTED)
                painter.setPen(self.SELECT_BORDER)
                painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            else:
                painter.fillRect(option.rect.adjusted(0, 0, 0, -1), self.INVALID_BG)

            painter.setPen(self.INVALID_FG)
            painter.drawText(option.rect.adjusted(4, 0, -4, 0), Qt.AlignLeft | Qt.AlignVCenter, text)

            painter.setPen(self.BORDER_COLOR)
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

            painter.restore()

    def setModelData(self, editor, model, index):
        text = editor.text().strip()
        model.setData(index, text, Qt.EditRole)


# ================= 通用文本控件 =================
class ElidedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(30)
        self.setToolTip(text)
        super().setText(text)

    def setFullText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self._apply_elide()

    def _apply_elide(self):
        fm = self.fontMetrics()
        avail = max(self.width() - 2, 0)
        super().setText(fm.elidedText(self._full_text, Qt.ElideMiddle, avail))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        if option.currentText == "（空白）":
            option.currentText = ""

        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)


class ComboCellDelegate(QStyledItemDelegate):
    def __init__(self, options, parent=None):
        super().__init__(parent)
        self._options = options

    def _get_options(self):
        opts = self._options() if callable(self._options) else self._options
        return opts or []

    def createEditor(self, parent, option, index):
        combo = NoWheelComboBox(parent)
        combo.setStyleSheet("QComboBox { border: 1px solid #ccc; padding-left: 5px; background: #fff; }")
        combo.setFocusPolicy(Qt.StrongFocus)

        for display, data in self._get_options():
            combo.addItem(display, data)

        if combo.count() > 0:
            combo.view().setTextElideMode(Qt.ElideNone)
            combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 20)
            QTimer.singleShot(10, combo.showPopup)
        return combo

    def setEditorData(self, editor, index):
        if not editor: return
        text = index.data(Qt.DisplayRole) or ""
        idx = editor.findText(text)
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        if not editor: return
        val = editor.currentData()
        if val is None: val = ""
        model.setData(index, val, Qt.EditRole)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(ROW_SELECTED_BG))
        else:
            # ★ 修复：优先读取单元格背景色（支持拉黑变红）
            bg = index.data(Qt.BackgroundRole)
            if bg:
                painter.fillRect(option.rect, bg)
            else:
                painter.fillRect(option.rect, QColor("#FFFFFF"))

        text = index.data(Qt.DisplayRole)
        if text:
            painter.setPen(QColor(TEXT_DARK))
            painter.drawText(option.rect.adjusted(5, 0, -20, 0), Qt.AlignLeft | Qt.AlignVCenter, str(text))

        draw_arrow(painter, option.rect)
        painter.restore()


class StatusComboDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        model = index.model()
        comp_time = model.index(index.row(), 8).data()
        if comp_time and str(comp_time).strip():
            return None

        combo = NoWheelComboBox(parent)
        combo.setStyleSheet("QComboBox { border: 1px solid #ccc; padding-left: 5px; background: #fff; }")
        combo.setFocusPolicy(Qt.StrongFocus)

        combo.addItem("（空白）", "")
        combo.addItem("已失效", "已失效")

        combo.view().setTextElideMode(Qt.ElideNone)
        combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 20)
        QTimer.singleShot(10, combo.showPopup)
        return combo

    def setEditorData(self, editor, index):
        if not editor: return
        text = index.data(Qt.DisplayRole)
        if not text or str(text).strip() == "":
            text = "（空白）"
        idx = editor.findText(text)
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        if not editor: return
        val = editor.currentData()
        if val is None: val = ""
        model.setData(index, val, Qt.EditRole)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(ROW_SELECTED_BG))
        else:
            painter.fillRect(option.rect, QColor("#FFFFFF"))

        val = index.data(Qt.DisplayRole)
        text = str(val).strip() if val else ""

        if text == "已失效":
            painter.setPen(QColor(TOGGLE_GREEN))
            font = option.font
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(option.rect.adjusted(5, 0, -20, 0), Qt.AlignLeft | Qt.AlignVCenter, text)
        elif text:
            painter.setPen(QColor(TEXT_DARK))
            painter.drawText(option.rect.adjusted(5, 0, -20, 0), Qt.AlignLeft | Qt.AlignVCenter, text)

        comp_time = index.model().index(index.row(), 8).data()
        if not (comp_time and str(comp_time).strip()):
            draw_arrow(painter, option.rect)

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            comp_time = model.index(index.row(), 8).data()
            if comp_time and str(comp_time).strip():
                return False
            return True
        return super().editorEvent(event, model, option, index)


class ExcelFilterProxyModel(QSortFilterProxyModel):
    filterChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter_dict = {}

    def set_filter(self, column, allowed_values):
        if allowed_values is None:
            self.filter_dict.pop(column, None)
        else:
            self.filter_dict[column] = allowed_values
        self.invalidateFilter()

        if self.parent() and hasattr(self.parent(), 'table'):
            self.parent().table.horizontalHeader().viewport().update()

        self.filterChanged.emit()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()

        if all(not str(model.data(model.index(source_row, c), Qt.DisplayRole) or "").strip()
               for c in range(1, model.columnCount())):
            return True

        for col, allowed in self.filter_dict.items():
            idx = model.index(source_row, col, source_parent)
            val = model.data(idx, Qt.DisplayRole)
            if val is None:
                val = ""
            if col == 0:
                continue

            if str(val) not in allowed:
                return False
        return True


class CheckListDelegate(QStyledItemDelegate):
    def __init__(self, parent_widget, list_widget, **style_kwargs):
        super().__init__(list_widget)
        self.parent_widget = parent_widget
        self.list_widget = list_widget
        self.style_kwargs = style_kwargs

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect
        if option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, QColor(BG_HOVER))

        item = self.list_widget.item(index.row())
        is_checked = item.checkState() == Qt.Checked if item else False

        left_box_rect = QRect(rect.left() + 5, rect.top(), 30, rect.height())
        draw_checkbox(painter, left_box_rect, is_checked, **self.style_kwargs)

        text = index.data(Qt.DisplayRole)
        text_rect = QRect(rect.left() + 40, rect.top(), rect.width() - 130, rect.height())
        painter.setPen(QColor(TEXT_DARK))
        font = option.font
        font.setPointSize(10)
        painter.setFont(font)

        # ★ 增加省略号截断，防止长文本撑破横向滚动条
        elided_text = painter.fontMetrics().elidedText(text, Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_text)

        if option.state & QStyle.State_MouseOver:
            btn_text = "仅筛选此项"
            btn_width = 80
            btn_height = 24
            btn_rect = QRect(rect.right() - btn_width - 10,
                             rect.top() + (rect.height() - btn_height) // 2,
                             btn_width, btn_height)
            painter.setBrush(QColor(ROW_SELECTED_BG))
            painter.setPen(QPen(QColor(TOGGLE_GREEN), 1))
            painter.drawRoundedRect(btn_rect, 4, 4)
            painter.setPen(QColor(TOGGLE_GREEN))
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(btn_rect, Qt.AlignCenter, btn_text)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            rect = option.rect
            btn_text = "仅筛选此项"
            btn_width = 80
            btn_height = 24
            btn_rect = QRect(rect.right() - btn_width - 10,
                             rect.top() + (rect.height() - btn_height) // 2,
                             btn_width, btn_height)
            if btn_rect.contains(event.pos()):
                if hasattr(self.parent_widget, 'filter_only_this_row'):
                    self.parent_widget.filter_only_this_row(index.row())
                return True
            item = self.list_widget.item(index.row())
            if item:
                new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                item.setCheckState(new_state)
                if hasattr(self.parent_widget, 'update_select_all_btn_state'):
                    self.parent_widget.update_select_all_btn_state()
                self.list_widget.viewport().update()
            return True
        return super().editorEvent(event, model, option, index)


class AdvancedFilterWidget(QWidget):
    def __init__(self, column, unique_values, current_allowed, parent=None, proxy_model=None):
        super().__init__(parent)
        self.column = column
        self.unique_values = unique_values
        self.current_allowed = current_allowed
        if proxy_model is not None:
            self.proxy_model = proxy_model
        else:
            self.proxy_model = parent.parent().model() if parent and parent.parent() else None

        self.setWindowFlags(Qt.Popup)

        # ★ 固定尺寸，避免外层 adjustSize 压缩导致高度不够
        self.setFixedSize(360, 420)

        self.setStyleSheet(f"""
            QWidget {{ background-color: #FFFFFF; border-radius: 6px; border: 1px solid #E5E7EB; }}
            QListWidget {{ 
                border: none; 
                outline: none; 
                background-color: transparent; 
            }}
            /* ★ 美化垂直滚动条 */
            QScrollBar:vertical {{
                border: none;
                background: #F3F4F6;
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: #D1D5DB;
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #9CA3AF;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QPushButton {{ border: none; background: transparent; color: {TEXT_DARK}; font-size: 13px; padding: 4px 6px; border-radius: 4px; }}
            QPushButton:hover {{ background-color: #F3F4F6; color: {TOGGLE_GREEN}; }}
            QLineEdit {{ border: 1px solid #DCDCDC; border-radius: 4px; padding: 4px 8px; font-size: 12px; background-color: #FAFAFA; }}
            QLineEdit:focus {{ border: 1px solid {TOGGLE_GREEN}; background-color: #FFFFFF; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(2)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setCursor(Qt.PointingHandCursor)
        self.btn_select_all.clicked.connect(self.toggle_select_all)

        btn_invert = QPushButton("反选")
        btn_invert.setCursor(Qt.PointingHandCursor)
        btn_invert.clicked.connect(self.invert_select)

        btn_dup = QPushButton("重复项")
        btn_dup.setCursor(Qt.PointingHandCursor)
        btn_dup.clicked.connect(self.select_dup)

        btn_unique = QPushButton("唯一项")
        btn_unique.setCursor(Qt.PointingHandCursor)
        btn_unique.clicked.connect(self.select_unique)

        def add_separator(lay):
            line = QLabel("|")
            line.setStyleSheet("color: #E0E0E0; font-size: 12px;")
            lay.addWidget(line)

        top_layout.addWidget(self.btn_select_all)
        add_separator(top_layout)
        top_layout.addWidget(btn_invert)
        add_separator(top_layout)
        top_layout.addWidget(btn_dup)
        add_separator(top_layout)
        top_layout.addWidget(btn_unique)
        top_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("模糊筛选...")
        self.search_input.setFixedWidth(85)
        self.search_input.textChanged.connect(self.filter_list_items)
        top_layout.addWidget(self.search_input)

        layout.addLayout(top_layout)

        self.list_widget = QListWidget()
        self.list_widget.setMouseTracking(True)
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        # ★ 禁用横向滚动条
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.delegate = CheckListDelegate(self, self.list_widget)
        self.list_widget.setItemDelegate(self.delegate)
        layout.addWidget(self.list_widget)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(
            "padding: 6px 16px; border: 1px solid #D1D5DB; border-radius: 6px; background-color: #FFFFFF;")
        btn_cancel.clicked.connect(self.close)

        btn_ok = QPushButton("确定")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet(
            f"background-color: {TOGGLE_GREEN}; color: white; border-radius: 6px; padding: 6px 20px; font-weight: bold;")
        btn_ok.clicked.connect(self.apply_filter)

        bottom_layout.addWidget(btn_cancel)
        bottom_layout.addWidget(btn_ok)
        layout.addLayout(bottom_layout)

        self.populate_list()

    def populate_list(self):
        self.list_widget.clear()
        counts = {}
        model = self.proxy_model.sourceModel() if self.proxy_model else None
        if not model: return

        for row in range(model.rowCount()):
            idx = model.index(row, self.column)
            val = str(model.data(idx, Qt.DisplayRole) or "")
            counts[val] = counts.get(val, 0) + 1
        sorted_vals = sorted(counts.keys())
        for val in sorted_vals:
            count = counts[val]
            display_text = f"{val if val else '(空白)'} ({count})"
            item = QListWidgetItem(display_text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if val in self.current_allowed else Qt.Unchecked)
            item.setData(Qt.UserRole, val)
            self.list_widget.addItem(item)
        self.update_select_all_btn_state()

    def filter_list_items(self, text):
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())

    def toggle_select_all(self):
        total_count = self.list_widget.count()
        if total_count == 0:
            return
        checked_count = sum(1 for i in range(total_count)
                            if self.list_widget.item(i).checkState() == Qt.Checked)
        target_state = Qt.Unchecked if checked_count == total_count else Qt.Checked
        self.list_widget.blockSignals(True)
        for i in range(total_count):
            self.list_widget.item(i).setCheckState(target_state)
        self.list_widget.blockSignals(False)
        self.update_select_all_btn_state()
        self.list_widget.viewport().update()

    def update_select_all_btn_state(self):
        total_count = self.list_widget.count()
        if total_count == 0:
            self.btn_select_all.setText("全选")
            return
        checked_count = sum(1 for i in range(total_count)
                            if self.list_widget.item(i).checkState() == Qt.Checked)
        self.btn_select_all.setText(f"全选 ({checked_count}/{total_count})")

    def filter_only_this_row(self, row):
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            it.setCheckState(Qt.Checked if i == row else Qt.Unchecked)
        self.list_widget.viewport().update()
        self.apply_filter()

    def invert_select(self):
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
        self.update_select_all_btn_state()
        self.list_widget.viewport().update()

    def select_dup(self):
        counts = {}
        model = self.proxy_model.sourceModel()
        for row in range(model.rowCount()):
            val = str(model.data(model.index(row, self.column), Qt.DisplayRole) or "")
            counts[val] = counts.get(val, 0) + 1
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            val = it.data(Qt.UserRole)
            it.setCheckState(Qt.Checked if counts.get(val, 0) > 1 else Qt.Unchecked)
        self.update_select_all_btn_state()
        self.list_widget.viewport().update()

    def select_unique(self):
        counts = {}
        model = self.proxy_model.sourceModel()
        for row in range(model.rowCount()):
            val = str(model.data(model.index(row, self.column), Qt.DisplayRole) or "")
            counts[val] = counts.get(val, 0) + 1
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            val = it.data(Qt.UserRole)
            it.setCheckState(Qt.Checked if counts.get(val, 0) == 1 else Qt.Unchecked)
        self.update_select_all_btn_state()
        self.list_widget.viewport().update()

    def apply_filter(self):
        selected_vals = set()
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.checkState() == Qt.Checked:
                selected_vals.add(it.data(Qt.UserRole))

        if self.proxy_model and hasattr(self.proxy_model, 'set_filter'):
            if len(selected_vals) == self.list_widget.count():
                self.proxy_model.set_filter(self.column, None)
            else:
                self.proxy_model.set_filter(self.column, selected_vals)
        self.close()


class FilterHeaderView(QHeaderView):
    """全软件统一表头：第 0 列全选，其余列单击弹出筛选弹窗（拖动列宽不触发）。"""

    def __init__(self, orientation, parent=None,
                 header_bg=HEADER_BG_COLOR,
                 header_filtered_bg=HEADER_FILTERED_BG_COLOR,
                 triangle_color=HEADER_TRIANGLE_COLOR,
                 triangle_active_color=HEADER_TRIANGLE_ACTIVE_COLOR,
                 show_checkbox=True,
                 show_filter=True,
                 **check_style_kwargs):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.active_popup = None
        self.show_checkbox = show_checkbox
        self.show_filter = show_filter

        self._press_pos = None

        self.header_bg = header_bg
        self.header_filtered_bg = header_filtered_bg
        self.triangle_color = triangle_color
        self.triangle_active_color = triangle_active_color
        self.check_style_kwargs = check_style_kwargs

    def paintSection(self, painter, rect, logical_index):
        if logical_index == -1:
            painter.fillRect(rect, QColor(self.header_bg))
            return

        model = self.parent().model()

        if logical_index == 0 and self.show_checkbox:
            painter.fillRect(rect, QColor(self.header_bg))
            all_checked = True
            has_data = False
            for row in range(model.rowCount()):
                idx = model.index(row, 0)
                if not model.data(idx, Qt.UserRole):
                    continue
                has_data = True
                if model.data(idx, Qt.CheckStateRole) != Qt.Checked:
                    all_checked = False
                    break
            if not has_data:
                all_checked = False
            draw_checkbox(painter, rect, all_checked, **self.check_style_kwargs)
            return

        is_filtered = hasattr(model, 'filter_dict') and logical_index in model.filter_dict
        painter.save()
        painter.fillRect(rect, QColor(self.header_filtered_bg if is_filtered else self.header_bg))
        super().paintSection(painter, rect, logical_index)
        painter.restore()

        if self.show_filter:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(self.triangle_active_color if is_filtered else self.triangle_color))
            painter.setPen(Qt.NoPen)
            tw, th = 8, 5
            x = rect.right() - 16
            y = rect.top() + (rect.height() - th) / 2
            painter.drawPolygon(QPolygon([QPoint(x, y),
                                          QPoint(x + tw, y),
                                          QPoint(x + tw / 2, y + th)]))
            painter.restore()

    def mousePressEvent(self, event):
        self._press_pos = event.pos()
        super().mousePressEvent(event)

        logical_index = self.logicalIndexAt(event.pos())
        if logical_index == 0 and self.show_checkbox:
            self.toggle_all_visible()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        if event.button() == Qt.LeftButton and self._press_pos is not None:
            logical_index = self.logicalIndexAt(event.pos())

            if logical_index > 0 and (event.pos() - self._press_pos).manhattanLength() <= 3:
                model = self.parent().model()
                if self.show_filter and (hasattr(model, 'filter_dict') or hasattr(model, 'set_filter')):
                    self.show_advanced_filter(logical_index, event.globalPos())

            self._press_pos = None

    def toggle_all_visible(self):
        view = self.parent()
        model = view.model()
        sel_model = view.selectionModel()

        valid_rows = [r for r in range(model.rowCount())
                      if model.data(model.index(r, 0), Qt.UserRole)]
        if not valid_rows:
            return

        is_check_table = model.data(model.index(valid_rows[0], 0), Qt.CheckStateRole) is not None

        if is_check_table:
            all_checked = all(
                model.data(model.index(r, 0), Qt.CheckStateRole) == Qt.Checked
                for r in valid_rows
            )
            target_state = Qt.Unchecked if all_checked else Qt.Checked

            for r in valid_rows:
                if hasattr(view, "item"):
                    item = view.item(r, 0)
                    if item: item.setCheckState(target_state)
                else:
                    model.setData(model.index(r, 0), target_state, Qt.CheckStateRole)

            if target_state == Qt.Unchecked:
                sel_model.clearSelection()
            else:
                last_col = model.columnCount() - 1
                selection = QItemSelection()
                for r in valid_rows:
                    selection.select(model.index(r, 0), model.index(r, last_col))
                sel_model.select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

        else:
            all_selected = all(sel_model.isRowSelected(r, model.index(r, 0).parent())
                               for r in valid_rows)
            if all_selected:
                sel_model.clearSelection()
            else:
                last_col = model.columnCount() - 1
                selection = QItemSelection()
                for r in valid_rows:
                    selection.select(model.index(r, 0), model.index(r, last_col))
                sel_model.select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def show_advanced_filter(self, column, global_pos):
        view = self.parent()
        model = view.model()
        source_model = model.sourceModel() if hasattr(model, 'sourceModel') else model
        unique_values = set()
        for row in range(source_model.rowCount()):
            val = source_model.data(source_model.index(row, column), Qt.DisplayRole)
            unique_values.add(str(val) if val is not None else "")

        filter_dict = getattr(model, 'filter_dict', {})
        current_allowed = filter_dict.get(column, unique_values)

        if self.active_popup:
            self.active_popup.close()
            self.active_popup.deleteLater()
            self.active_popup = None

        # ★ 修复：将 model 直接传进去
        self.active_popup = AdvancedFilterWidget(column, unique_values, current_allowed, self.window(),
                                                 proxy_model=model)

        # ★ 强制立刻计算大小，拿到准确的宽高
        self.active_popup.ensurePolished()
        # 由于内部已经 self.setFixedSize，这里 adjustSize 不会覆盖它的 360x420 尺寸
        self.active_popup.adjustSize()
        w = self.active_popup.width()
        h = self.active_popup.height()

        # ★ 重新计算稳妥的坐标
        # 获取该列左边缘的全局 X 坐标
        col_x = self.mapToGlobal(QPoint(self.sectionViewportPosition(column), 0)).x()
        # 获取表头底部的全局 Y 坐标
        header_bottom_y = self.mapToGlobal(QPoint(0, self.height())).y()

        x = col_x
        y = header_bottom_y + 2  # 留一点小缝隙

        screen = QApplication.screenAt(global_pos)
        if not screen:
            screen = QApplication.primaryScreen()

        if screen:
            sr = screen.availableGeometry()

            # 右侧越界防出屏
            if x + w > sr.right():
                x = sr.right() - w - 10
            # 左侧越界防出屏
            if x < sr.left():
                x = sr.left() + 10

            # 下方越界防出屏（翻转到表头上方）
            if y + h > sr.bottom():
                # ★ 精准反转：紧贴在表头上方
                y = header_bottom_y - self.height() - h - 2

        self.active_popup.move(x, y)
        self.active_popup.show()
        self.active_popup.setFocus()


class CenteredCheckBoxDelegate(QStyledItemDelegate):
    def __init__(self, parent=None,
                 selected_bg=ROW_SELECTED_BG,
                 hover_bg=ROW_HOVER_BG,
                 **style_kwargs):
        super().__init__(parent)
        self.selected_bg = selected_bg
        self.hover_bg = hover_bg
        self.style_kwargs = style_kwargs

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(self.selected_bg))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(self.hover_bg))

        checked = (index.data(Qt.CheckStateRole) == Qt.Checked) or \
                  bool(option.state & QStyle.State_Selected)

        draw_checkbox(painter, option.rect, checked, **self.style_kwargs)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            return True
        return super().editorEvent(event, model, option, index)


class HintPopup(QWidget):
    MAX_WIDTH = 400

    def __init__(self, text, anchor):
        super().__init__(anchor.window(), Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setObjectName("HintPopup")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)

        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._label.setStyleSheet(
            f"color: {TEXT_DARK}; font-size: 13px; background: transparent; border: none;"
        )
        layout.addWidget(self._label)

        self.setStyleSheet("""
            #HintPopup {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
            }
        """)

        self.setMaximumWidth(self.MAX_WIDTH)
        self.adjustSize()
        self._position_near(anchor)

    def _position_near(self, anchor):
        anchor_bottom = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        x = anchor_bottom.x()
        y = anchor_bottom.y()

        screen = QApplication.screenAt(anchor_bottom)
        if screen:
            sr = screen.availableGeometry()
            if x + self.width() > sr.right():
                x = sr.right() - self.width() - 8
            if x < sr.left():
                x = sr.left() + 8
            if y + self.height() > sr.bottom():
                anchor_top = anchor.mapToGlobal(QPoint(0, 0))
                y = anchor_top.y() - self.height() - 4

        self.move(x, y)


class HintButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__("💡", parent)
        self._text = text
        self._popup = None
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击查看提示")
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(28, 28)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 15px;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
                border-radius: 14px;
            }}
        """)
        self.clicked.connect(self._show_popup)

    def setHintText(self, text):
        self._text = text

    def _show_popup(self):
        if self._popup is not None:
            self._popup.deleteLater()
            self._popup = None
        self._popup = HintPopup(self._text, self)
        self._popup.show()