# page_spider.py
# ================================================================
# ★ 待抓取页面分类维护说明
# ----------------------------------------------------------------
# 待抓取页显示的 sites 数据 = 从 sites 表中"排除"以下分类后的结果：
#
#   1. 在 PLATFORM_DOMAINS 注册过域名的分类
#      （网盘 / 知道 / 贴吧 / 暂未开通 等，链接本身就是资源页，无需抓章节）
#   2. 搜索引擎（百度搜索 / 夸克搜索 / uc搜索）
#
# 其余分类（如 "其他" 以及以后新增的小说站/资源站）视为
# 【一般网站资源】，会出现在待抓取页，供抓取章节。
#
# 如果要让一个新分类【不进】待抓取页：
#   → 去 app_data/complaint_platform_consts.py 的 PLATFORM_DOMAINS 里
#     为该分类注册一个域名（顺便 PLATFORM_CONFIG 也要注册显示名），
#     本文件会自动生效，无需改动。
#
# 如果要让一个新分类【进】待抓取页（普通小说站）：
#   → 只在 PLATFORM_CONFIG 注册显示名，【不要】加进 PLATFORM_DOMAINS 即可。
#
# 排除名单的推导逻辑见 app_data/spider_consts.py。
# ================================================================
import sqlite3
import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QHeaderView, QMessageBox, QAbstractItemView,
                               QPushButton, QApplication, QComboBox, QLineEdit, QDialog,
                               QTableView, QFrame, QStyledItemDelegate, QStyle, QMenu,
                               QListWidget, QListWidgetItem, QStylePainter, QStyleOptionComboBox,
                               QSizePolicy)  # ★ 修复：补上 QSizePolicy
from PySide6.QtCore import (Qt, QUrl, QPoint, QRect, QEvent,
                            QItemSelection, QItemSelectionModel, QTimer)
from PySide6.QtGui import (QColor, QFont, QStandardItemModel, QStandardItem,
                           QPainter, QPen, QPainterPath, QPolygon, QCursor)

from playwright.sync_api import sync_playwright

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

from db_config import get_conn
from feature_extractor import extract_pure_feature
from chapter_extractor import is_target_chapter
from ui_components import (
    ExcelFilterProxyModel, FilterHeaderView, CenteredCheckBoxDelegate,
    CheckListDelegate,
    draw_checkbox,
    CHECK_BG_COLOR, CHECK_MARK_COLOR,
    HEADER_BG_COLOR, HEADER_FILTERED_BG_COLOR,
    HEADER_TRIANGLE_COLOR, HEADER_TRIANGLE_ACTIVE_COLOR,
)

# ★ 引入权限管理器
from license_manager import license_mgr

# ★ 待抓取页排除名单（从 PLATFORM_DOMAINS 推导，见 spider_consts.py）
from app_data.spider_consts import NO_CHAPTER_CRAWL_CATEGORIES


# ================= Spider 专属：状态下拉框与代理 =================
class SpiderNoWheelComboBox(QComboBox):
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


class SpiderStatusComboDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        table = option.widget
        if isinstance(table, QTableWidget):
            chk_item = table.item(index.row(), 0)
            if chk_item:
                data = chk_item.data(Qt.UserRole)
                if data and isinstance(data, dict) and data.get("comp_time", ""):
                    return None  # 有投诉时间，禁止编辑

        combo = SpiderNoWheelComboBox(parent)
        combo.setStyleSheet("QComboBox { border: 1px solid #ccc; padding-left: 5px; background: #fff; }")
        combo.setFocusPolicy(Qt.StrongFocus)

        combo.addItem("（空白）", "")
        combo.addItem("已失效", "已失效")

        QTimer.singleShot(10, combo.showPopup)
        return combo

    def setEditorData(self, editor, index):
        if not editor:
            return
        text = index.data(Qt.DisplayRole)
        if not text or str(text).strip() == "":
            text = "（空白）"
        idx = editor.findText(text)
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        if not editor:
            return
        val = editor.currentData()
        if val is None:
            val = ""
        model.setData(index, val, Qt.EditRole)

        table = editor.parent()
        while table and not isinstance(table, QTableWidget):
            table = table.parent()

        if table:
            chk_item = table.item(index.row(), 0)
            if chk_item:
                data = chk_item.data(Qt.UserRole)
                if data and isinstance(data, dict):
                    db_id = data.get("id")
                    if db_id:
                        conn = get_conn()
                        conn.execute("UPDATE sites SET resource_status=? WHERE id=?", (val, db_id))
                        conn.commit()
                        conn.close()

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#E8F5E9"))
        else:
            painter.fillRect(option.rect, QColor("#FFFFFF"))

        val = index.data(Qt.DisplayRole)
        text = str(val).strip() if val else ""

        if text == "已失效":
            painter.setPen(QColor("#10B981"))
            font = option.font
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(option.rect.adjusted(5, 0, -20, 0), Qt.AlignLeft | Qt.AlignVCenter, text)
        elif text:
            painter.setPen(QColor("#333333"))
            painter.drawText(option.rect.adjusted(5, 0, -20, 0), Qt.AlignLeft | Qt.AlignVCenter, text)

        table = option.widget
        chk_item = None
        if isinstance(table, QTableWidget):
            chk_item = table.item(index.row(), 0)

        comp_time = ""
        if chk_item:
            data = chk_item.data(Qt.UserRole)
            if data and isinstance(data, dict):
                comp_time = data.get("comp_time", "")

        if not comp_time:
            x = option.rect.right() - 16
            y = option.rect.center().y() - 2
            points = [QPoint(x, y), QPoint(x + 8, y), QPoint(x + 4, y + 5)]
            painter.setBrush(QColor("#999999"))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygon(points))

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            table = option.widget
            chk_item = None
            if isinstance(table, QTableWidget):
                chk_item = table.item(index.row(), 0)

            if chk_item:
                data = chk_item.data(Qt.UserRole)
                if data and isinstance(data, dict) and data.get("comp_time", ""):
                    return False
            return True
        return super().editorEvent(event, model, option, index)


# ================= 名称筛选弹窗 =================
class NameFilterPopup(QFrame):
    def __init__(self, parent_table, current_filtered, on_apply):
        super().__init__(parent_table, Qt.Popup)
        self.parent_table = parent_table
        self.on_apply = on_apply
        self.filtered_names = list(current_filtered)

        self.setFixedSize(280, 420)
        self.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #CCCCCC; border-radius: 4px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(2)

        self.btn_select_all = QPushButton("全选")
        btn_invert = QPushButton("反选")
        btn_clear = QPushButton("清空")

        for btn in (self.btn_select_all, btn_invert, btn_clear):
            btn.setStyleSheet(
                "QPushButton { border: none; color: #333; font-size: 12px; "
                "padding: 2px 6px; background: transparent; }"
                "QPushButton:hover { color: #10B981; }"
            )

        self.btn_select_all.clicked.connect(self.select_all)
        btn_invert.clicked.connect(self.invert)
        btn_clear.clicked.connect(self.clear_all)

        top_layout.addWidget(self.btn_select_all)
        top_layout.addWidget(btn_invert)
        top_layout.addWidget(btn_clear)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        self.list_widget = QListWidget()
        self.list_widget.setMouseTracking(True)
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.setItemDelegate(CheckListDelegate(self, self.list_widget))
        self.list_widget.setStyleSheet(
            "QListWidget { border: none; outline: none; background: transparent; }"
        )
        layout.addWidget(self.list_widget)

        names = set()
        for row in range(parent_table.rowCount()):
            it = parent_table.item(row, 4)
            if it and it.text().strip():
                names.add(it.text().strip())
        for name in sorted(names):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if name in self.filtered_names else Qt.Checked)
            self.list_widget.addItem(item)
        self.update_select_all_btn_state()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(
            "padding: 5px 15px; border: 1px solid #ccc; border-radius: 4px; background-color: #fff;"
        )
        btn_cancel.clicked.connect(self.close)

        btn_ok = QPushButton("确定")
        btn_ok.setStyleSheet(
            "background-color: #10B981; color: white; border-radius: 4px; "
            "padding: 5px 20px; font-weight: bold;"
        )
        btn_ok.clicked.connect(self.apply_filter)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def update_select_all_btn_state(self):
        total = self.list_widget.count()
        if total == 0:
            self.btn_select_all.setText("全选")
            return
        checked = sum(1 for i in range(total)
                      if self.list_widget.item(i).checkState() == Qt.Checked)
        self.btn_select_all.setText(f"全选 ({checked}/{total})")

    def filter_only_this_row(self, row):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked if i == row else Qt.Unchecked)
        self.update_select_all_btn_state()
        self.list_widget.viewport().update()

    def _set_all(self, state):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)
        self.update_select_all_btn_state()
        self.list_widget.viewport().update()

    def select_all(self):
        self._set_all(Qt.Checked)

    def clear_all(self):
        self._set_all(Qt.Unchecked)

    def invert(self):
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
        self.update_select_all_btn_state()
        self.list_widget.viewport().update()

    def apply_filter(self):
        filtered = []
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.checkState() == Qt.Unchecked:
                filtered.append(it.text())
        self.on_apply(filtered)
        self.close()


# ================= 自定义表头（全选 + 名称筛选） =================
class SpiderHeaderView(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.active_popup = None
        self.filtered_names = []

        # ★ 记录按下坐标，用于区分拖拽和单击
        self._press_pos = None

    def paintSection(self, painter, rect, logical_index):
        if logical_index == -1:
            painter.fillRect(rect, QColor(HEADER_BG_COLOR))
            return

        if logical_index == 0:
            painter.fillRect(rect, QColor(HEADER_BG_COLOR))
            parent_table = self.parent()
            all_checked = True
            has_data = False
            if parent_table:
                for row in range(parent_table.rowCount()):
                    item = parent_table.item(row, 0)
                    if item and item.data(Qt.UserRole) is not None:
                        has_data = True
                        if item.checkState() != Qt.Checked:
                            all_checked = False
                            break
            if not has_data:
                all_checked = False
            draw_checkbox(painter, rect, all_checked)
            return

        painter.save()
        if logical_index == 4 and self.filtered_names:
            painter.fillRect(rect, QColor(HEADER_FILTERED_BG_COLOR))
        else:
            painter.fillRect(rect, QColor(HEADER_BG_COLOR))
        super().paintSection(painter, rect, logical_index)
        painter.restore()

        if logical_index == 4:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(
                HEADER_TRIANGLE_ACTIVE_COLOR if self.filtered_names else HEADER_TRIANGLE_COLOR
            ))
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
        if logical_index == 0:
            self.toggle_all()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        if event.button() == Qt.LeftButton and self._press_pos is not None:
            logical_index = self.logicalIndexAt(event.pos())

            # 判断：第 4 列，且没有发生明显拖拽（单击）
            if logical_index == 4 and (event.pos() - self._press_pos).manhattanLength() <= 3:
                self.show_name_filter(event.globalPos())

            self._press_pos = None

    def toggle_all(self):
        parent_table = self.parent()
        if not parent_table:
            return

        model = parent_table.model()
        sel_model = parent_table.selectionModel()

        valid_rows = []
        for r in range(parent_table.rowCount()):
            item = parent_table.item(r, 0)
            if item and item.data(Qt.UserRole) is not None and not parent_table.isRowHidden(r):
                valid_rows.append(r)

        if not valid_rows:
            return

        all_selected = all(
            sel_model.isRowSelected(r, model.index(r, 0).parent())
            for r in valid_rows
        )

        last_col = parent_table.columnCount() - 1
        selection = QItemSelection()
        for r in valid_rows:
            selection.select(model.index(r, 0), model.index(r, last_col))

        if all_selected:
            sel_model.select(selection,
                             QItemSelectionModel.Deselect | QItemSelectionModel.Rows)
        else:
            sel_model.select(selection,
                             QItemSelectionModel.Select | QItemSelectionModel.Rows)

        self.viewport().update()

    def show_name_filter(self, global_pos):
        parent_table = self.parent()
        if not parent_table:
            return
        if self.active_popup:
            self.active_popup.close()

        popup = NameFilterPopup(parent_table, self.filtered_names, self.apply_name_filter)
        self.active_popup = popup

        screen = QApplication.screenAt(global_pos)
        if screen:
            sr = screen.availableGeometry()
            x = global_pos.x() - 100
            y = global_pos.y() + 30
            if x + popup.width() > sr.right():
                x = sr.right() - popup.width() - 10
            if y + popup.height() > sr.bottom():
                y = global_pos.y() - popup.height() - 10
            popup.move(x, y)
        else:
            popup.move(global_pos.x() - 100, global_pos.y() + 30)
        popup.show()

    def apply_name_filter(self, filtered_names):
        self.filtered_names = filtered_names
        parent_table = self.parent()
        if parent_table:
            for row in range(parent_table.rowCount()):
                name_item = parent_table.item(row, 4)
                name_text = name_item.text().strip() if name_item else ""
                parent_table.setRowHidden(row, name_text in self.filtered_names)
        self.viewport().update()


# ================= 待抓取表格 =================
class SpiderSourceTable(QTableWidget):
    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid():
            if index.column() == 0:
                sel_model = self.selectionModel()
                is_selected = sel_model.isRowSelected(index.row(), index.parent())
                mods = event.modifiers()

                self.setCurrentIndex(index)

                if mods & (Qt.ControlModifier | Qt.ShiftModifier):
                    if is_selected:
                        sel_model.select(index, QItemSelectionModel.Deselect | QItemSelectionModel.Rows)
                    else:
                        sel_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                else:
                    if is_selected:
                        sel_model.select(index, QItemSelectionModel.Deselect | QItemSelectionModel.Rows)
                    else:
                        sel_model.select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

                event.accept()
                return
            elif index.column() == 8:
                chk_item = self.item(index.row(), 0)
                if chk_item:
                    data = chk_item.data(Qt.UserRole)
                    if data and isinstance(data, dict) and data.get("comp_time", ""):
                        return  # 有投诉时间，拦截点击

                self.setCurrentIndex(index)
                self.edit(index)
                event.accept()
                return

        super().mousePressEvent(event)


class WebPreviewDialog(QDialog):
    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"网页预览 - {url}")
        self.resize(1000, 800)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if QWebEngineView:
            self.browser = QWebEngineView()
            self.browser.setUrl(QUrl(url))
            layout.addWidget(self.browser)
        else:
            label = QLabel("未检测到 QWebEngineView 模块，无法预览网页。")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)


class SpiderPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ================= 1. 顶部标题区 =================
        title_layout = QHBoxLayout()
        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(8)
        main_title = QLabel("【待抓取的页面】")
        main_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1F1F1F;")
        sub_title = QLabel("双击任意行的“页面链接”即可预览网页。勾选后点击右侧按钮开始提取章节。")
        sub_title.setStyleSheet("font-size: 13px; color: #888888;")
        sub_title.setWordWrap(True) # ★ 加上防撑爆换行
        title_vbox.addWidget(main_title)
        title_vbox.addWidget(sub_title)
        title_layout.addLayout(title_vbox)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # ================= 2. 卡片式工具栏 =================
        tool_frame = QFrame()
        tool_frame.setStyleSheet("""
            QFrame {
                background-color: #F8F9FA;
                border: 1px solid #E9ECEF;
                border-radius: 6px;
            }
        """)
        tool_layout = QHBoxLayout(tool_frame)
        tool_layout.setContentsMargins(15, 10, 15, 10)
        tool_layout.setSpacing(10)

        lbl_status = QLabel("状态筛选:")
        lbl_status.setStyleSheet("color: #495057; font-weight: bold; border: none;")
        tool_layout.addWidget(lbl_status)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部状态", "仅未抓取", "仅已抓取", "已投诉", "已失效"])
        self.status_filter.setCurrentIndex(1)
        self.status_filter.setStyleSheet("""
            QComboBox { border: 1px solid #CCCCCC; border-radius: 4px; padding: 4px 8px; background: #FFF; min-width: 100px; color: #333; }
            QComboBox:hover { border: 1px solid #1F1F1F; }
        """)
        self.status_filter.currentTextChanged.connect(self.refresh_data)
        tool_layout.addWidget(self.status_filter)

        tool_layout.addSpacing(20)

        lbl_rule = QLabel("章节提取规则:")
        lbl_rule.setStyleSheet("color: #495057; font-weight: bold; border: none;")
        tool_layout.addWidget(lbl_rule)

        self.rule_combo = QComboBox()
        self.rule_combo.addItems(["第X章", "第X节", "分节阅读X", "纯数字", "自定义关键字"])
        self.rule_combo.setStyleSheet("""
            QComboBox { border: 1px solid #CCCCCC; border-radius: 4px; padding: 4px 8px; background: #FFF; min-width: 100px; color: #333; }
            QComboBox:hover { border: 1px solid #1F1F1F; }
        """)
        self.rule_combo.currentTextChanged.connect(self.toggle_custom_input)
        tool_layout.addWidget(self.rule_combo)

        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText("关键字")
        self.custom_input.setFixedWidth(100)
        self.custom_input.setStyleSheet("""
            QLineEdit { border: 1px solid #CCCCCC; border-radius: 4px; padding: 4px 8px; background: #FFF; color: #333; }
            QLineEdit:focus { border: 1px solid #1F1F1F; }
        """)
        self.custom_input.hide()
        tool_layout.addWidget(self.custom_input)

        tool_layout.addStretch()

        self.crawl_btn = QPushButton("🔗 开始抓取/提取")
        self.crawl_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #9CA3AF; }
        """)
        self.crawl_btn.clicked.connect(self.start_crawl)
        tool_layout.addWidget(self.crawl_btn)

        layout.addWidget(tool_frame)

        # ================= 3. 待抓取表格 =================
        self.source_table = SpiderSourceTable()
        self.source_table.setColumnCount(9)
        self.source_table.setHorizontalHeaderLabels(
            ["勾选", "关联作品", "分类", "页面链接", "名称", "属性", "抓取状态", "投诉时间", "资源状态"])

        self.source_table.verticalHeader().setFixedWidth(35)
        self.source_table.verticalHeader().setDefaultSectionSize(35)

        custom_header = SpiderHeaderView(Qt.Horizontal, self.source_table)
        self.source_table.setHorizontalHeader(custom_header)

        header_src = self.source_table.horizontalHeader()
        header_src.setSectionResizeMode(QHeaderView.Stretch)
        header_src.setSectionResizeMode(0, QHeaderView.Fixed)
        header_src.setSectionResizeMode(8, QHeaderView.Fixed)
        self.source_table.setColumnWidth(0, 45)
        self.source_table.setColumnWidth(8, 100)

        self.source_table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(self.source_table))
        self.source_table.setItemDelegateForColumn(8, SpiderStatusComboDelegate(self.source_table))

        self.source_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.source_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.source_table.setMaximumHeight(220)
        self.source_table.cellDoubleClicked.connect(self.on_cell_double_clicked)

        self.source_table.selectionModel().selectionChanged.connect(self.on_source_selection_changed)

        self.source_table.setStyleSheet("""
            QTableWidget { border: 1px solid #E9ECEF; background-color: #FFFFFF; }
            QTableWidget::item:selected { background-color: #E3F2FD; color: #333; }
        """)
        self.source_table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding) # ★ 防撑爆
        layout.addWidget(self.source_table)

        # ================= 4. 提取结果区 =================
        result_title = QLabel("【提取结果】")
        result_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1F1F1F; margin-top: 10px;")
        layout.addWidget(result_title)

        self.result_model = QStandardItemModel(0, 6, self)
        self.result_model.setHorizontalHeaderLabels(
            ["勾选", "关联作品", "提取到的链接", "分类", "名称(可修改)", "属性(可修改)"])

        self.proxy_model = ExcelFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.result_model)

        self.result_view = QTableView()
        self.result_view.setModel(self.proxy_model)

        self.result_view.setStyleSheet("""
            QTableView { border: 1px solid #E9ECEF; background-color: #FFFFFF; }
            QTableView::item:selected { background-color: #E3F2FD; color: #333; }
        """)

        res_header = FilterHeaderView(Qt.Horizontal, self.result_view)
        self.result_view.setHorizontalHeader(res_header)
        self.result_view.horizontalHeader().setFixedHeight(35)

        self.result_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.result_view.setColumnWidth(0, 45)

        self.result_view.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(self.result_view))

        self.result_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_view.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)

        self.result_view.verticalHeader().setFixedWidth(35)
        self.result_view.selectionModel().selectionChanged.connect(self.on_result_selection_changed)

        self.result_view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding) # ★ 防撑爆
        layout.addWidget(self.result_view)

        # ================= 5. 保存按钮 =================
        self.save_btn = QPushButton("将勾选结果保存到盗版链接库")
        self.save_btn.setStyleSheet("""
            QPushButton { background-color: #10B981; color: white; padding: 10px; border-radius: 4px; font-weight: bold; font-size: 14px; border: none; }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #9CA3AF; }
        """)
        self.save_btn.clicked.connect(self.save_results)
        layout.addWidget(self.save_btn)

        # ★ 权限拦截：初始化时检查是否过期，如果过期直接禁用按钮
        if license_mgr.is_expired:
            tip = "您的会员已过期，无法使用高级功能。请联系管理员续费。"
            self.crawl_btn.setEnabled(False)
            self.crawl_btn.setToolTip(tip)
            self.save_btn.setEnabled(False)
            self.save_btn.setToolTip(tip)

    def on_source_selection_changed(self, selected, deselected):
        selected_rows = set(idx.row() for idx in selected.indexes())
        deselected_rows = set(idx.row() for idx in deselected.indexes())
        deselected_rows -= selected_rows

        self.source_table.blockSignals(True)
        for r in deselected_rows:
            chk = self.source_table.item(r, 0)
            if chk:
                chk.setCheckState(Qt.Unchecked)
        for r in selected_rows:
            chk = self.source_table.item(r, 0)
            if chk:
                chk.setCheckState(Qt.Checked)
        self.source_table.blockSignals(False)
        self.source_table.viewport().update()
        self.source_table.horizontalHeader().viewport().update()

    def on_result_selection_changed(self, selected, deselected):
        selected_rows = set(idx.row() for idx in selected.indexes())
        deselected_rows = set(idx.row() for idx in deselected.indexes())
        deselected_rows -= selected_rows

        for r in deselected_rows:
            src_idx = self.proxy_model.mapToSource(self.proxy_model.index(r, 0))
            item = self.result_model.item(src_idx.row(), 0)
            if item and item.data(Qt.UserRole) is not None:
                if item.checkState() != Qt.Unchecked:
                    item.setCheckState(Qt.Unchecked)

        for r in selected_rows:
            src_idx = self.proxy_model.mapToSource(self.proxy_model.index(r, 0))
            item = self.result_model.item(src_idx.row(), 0)
            if item and item.data(Qt.UserRole) is not None:
                if item.checkState() != Qt.Checked:
                    item.setCheckState(Qt.Checked)
        self.result_view.viewport().update()

    def toggle_custom_input(self, text):
        if text == "自定义关键字":
            self.custom_input.show()
        else:
            self.custom_input.hide()

    def on_cell_double_clicked(self, row, column):
        if column == 3:
            url = self.source_table.item(row, 3).text()
            if url:
                dialog = WebPreviewDialog(url, self)
                dialog.exec()

    def refresh_data(self):
        self.source_table.setRowCount(0)
        conn = get_conn()
        cursor = conn.cursor()

        # ★ 排除名单从 spider_consts 推导（见文件顶部说明）。
        #   凡是在 PLATFORM_DOMAINS 注册了域名的分类（网盘 / 知道 / 贴吧 / 暂未开通）
        #   + 搜索引擎，都不出现在待抓取页；其余视为一般网站资源，需要抓章节。
        excluded = list(NO_CHAPTER_CRAWL_CATEGORIES)
        placeholders = ",".join("?" * len(excluded))

        # ★ 用 COALESCE 兜底，避免 category 为 NULL 时 NOT IN 结果非 True 导致整行漏掉
        query = f'''SELECT s.id,
                           COALESCE(b.name, s.book_name) as real_book_name,
                           s.category,
                           s.site_url,
                           s.name,
                           s.attr,
                           s.crawl_status,
                           s.resource_status,
                           s.complaint_time
                    FROM sites s
                    LEFT JOIN books b ON s.book_id = b.id
                    WHERE COALESCE(s.category, '') NOT IN ({placeholders})'''
        params = list(excluded)

        filter_text = self.status_filter.currentText()
        if filter_text == "仅未抓取":
            query += (" AND (s.crawl_status IS NULL OR s.crawl_status = '')"
                      " AND (s.resource_status IS NULL OR s.resource_status = '')"
                      " AND (s.complaint_time IS NULL OR s.complaint_time = '')")
        elif filter_text == "仅已抓取":
            query += " AND s.crawl_status = '已抓取'"
        elif filter_text == "已投诉":
            query += " AND s.complaint_time IS NOT NULL AND s.complaint_time != ''"
        elif filter_text == "已失效":
            query += " AND s.resource_status = '已失效'"

        query += " ORDER BY s.id DESC"
        records = cursor.execute(query, params).fetchall()
        conn.close()

        for row_data in records:
            db_id, book_name, cat, url, name, attr, crawl_status, res_status, comp_time = row_data
            row = self.source_table.rowCount()
            self.source_table.insertRow(row)

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, {"id": db_id, "comp_time": comp_time})
            self.source_table.setItem(row, 0, chk)

            for col_idx, text in enumerate(
                    [book_name or "未关联", cat or "未分类", url, name or "", attr or "", crawl_status or ""],
                    start=1):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if col_idx == 3:
                    item.setToolTip("双击此行此列可预览网页")
                if col_idx == 6 and crawl_status == '已抓取':
                    item.setForeground(QColor("#10B981"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.source_table.setItem(row, col_idx, item)

            comp_time_item = QTableWidgetItem(comp_time or "")
            comp_time_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.source_table.setItem(row, 7, comp_time_item)

            display_status = ""
            if not comp_time and res_status == "已失效":
                display_status = "已失效"

            status_item = QTableWidgetItem(display_status)
            status_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.source_table.setItem(row, 8, status_item)

        self.source_table.horizontalHeader().filtered_names = []
        self.source_table.horizontalHeader().viewport().update()

    def start_crawl(self):
        # ★ 逻辑层拦截
        if license_mgr.is_expired:
            QMessageBox.warning(self, "授权已过期",
                                "您的会员已过期，无法使用网页抓取功能。\n请前往【个人中心】查看详情或联系管理员续费。")
            return

        rule = self.rule_combo.currentText()
        custom_kw = self.custom_input.text().strip()

        if rule == "自定义关键字" and not custom_kw:
            QMessageBox.warning(self, "提示", "请输入自定义关键字！")
            return

        rows_to_crawl = []
        for r in range(self.source_table.rowCount()):
            if self.source_table.isRowHidden(r):
                continue

            chk_item = self.source_table.item(r, 0)
            if chk_item and chk_item.checkState() == Qt.Checked:
                data = chk_item.data(Qt.UserRole)
                db_id = data.get("id") if isinstance(data, dict) else None

                book_name = self.source_table.item(r, 1).text()
                if book_name == "未关联":
                    book_name = ""
                cat = self.source_table.item(r, 2).text()
                url = self.source_table.item(r, 3).text()
                name = self.source_table.item(r, 4).text()
                attr = self.source_table.item(r, 5).text()
                rows_to_crawl.append((db_id, book_name, cat, url, name, attr))

        if not rows_to_crawl:
            QMessageBox.warning(self, "提示", "请先勾选要抓取的网页！")
            return

        self.crawl_btn.setText("抓取中...")
        self.crawl_btn.setEnabled(False)
        QApplication.processEvents()

        self.result_model.removeRows(0, self.result_model.rowCount())
        self.proxy_model.filter_dict.clear()
        self.proxy_model.invalidateFilter()

        total_chapters = 0
        total_intros = 0
        failed_sites = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(ignore_https_errors=True)
                page = context.new_page()

                seen_codes = set()  # 跨网页去重

                for db_id, book_name, cat, url, src_name, src_attr in rows_to_crawl:
                    try:
                        self.crawl_btn.setText(f"加载中...")
                        QApplication.processEvents()

                        page.goto(url, timeout=20000, wait_until="domcontentloaded")
                        time.sleep(3)

                        html_content = page.content()
                        soup = BeautifulSoup(html_content, "html.parser")

                        c_count, i_count = self.extract_chapters(soup, url, book_name, cat, rule, custom_kw,
                                                                 src_name, db_id, seen_codes)
                        total_chapters += c_count
                        total_intros += i_count

                        if c_count == 0 and i_count == 0:
                            failed_sites.append(f"《{book_name or '未关联'}》- [{cat}]")

                    except Exception as e:
                        failed_sites.append(f"《{book_name or '未关联'}》- [{cat}] (加载失败)")
                        print(f"抓取异常: {e}")

                browser.close()

        finally:
            self.crawl_btn.setText("🔗 开始抓取/提取")
            # 恢复按钮时也要检查是否过期
            self.crawl_btn.setEnabled(not license_mgr.is_expired)

            if total_chapters > 0 or total_intros > 0 or failed_sites:
                msg = "抓取完成！\n\n"
                if total_chapters > 0:
                    msg += f"✅ 提取到【{rule}】链接：{total_chapters} 条\n"
                if total_intros > 0:
                    msg += f"✅ 提取到【内容简介】链接：{total_intros} 条\n"

                if failed_sites:
                    msg += f"\n⚠️ 以下 {len(failed_sites)} 个网站未抓取到内容，请确认抓取规则：\n"
                    for site in failed_sites:
                        msg += f" - {site}\n"

                QMessageBox.information(self, "抓取结果", msg)
            else:
                QMessageBox.warning(self, "未提取到新链接", "网页加载了，但没有找到符合规则的新内容。")

    def extract_chapters(self, soup, base_url, book_name, base_cat, rule, custom_kw, src_name, source_id, seen_codes):
        chapter_found = 0
        intro_found = 0
        conn = get_conn()
        cursor = conn.cursor()

        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            title = a.get_text(strip=True)
            if not title:
                continue

            if href.startswith("javascript:") or href.startswith("#"):
                continue

            is_intro = False
            if any(kw in title for kw in ["简介", "内容简介", "作品简介", "小说简介"]):
                match = re.search(r'《(.*?)》', title)
                if match:
                    t_book = match.group(1).strip()
                    if book_name and t_book != book_name:
                        is_intro = False
                    else:
                        is_intro = True
                else:
                    if book_name:
                        if title in ["简介", "内容简介", "作品简介", "小说简介", "《内容简介》", "返回简介", "查看简介"]:
                            is_intro = True
                        elif book_name in title:
                            is_intro = True
                        else:
                            is_intro = False
                    else:
                        is_intro = True

            is_chapter = is_target_chapter(title, rule, custom_kw)

            if is_chapter or is_intro:
                code = extract_pure_feature(href)
                if code in seen_codes:
                    continue
                if cursor.execute("SELECT id FROM sites WHERE feature_code=?", (code,)).fetchone():
                    continue

                seen_codes.add(code)

                if is_intro:
                    intro_found += 1
                    attr_text = "抓取 内容简介"
                else:
                    chapter_found += 1
                    attr_text = f"抓取 {title}"

                self.add_result_row(book_name, href, base_cat, title=title, name=src_name,
                                    attr=attr_text, source_id=source_id)

        conn.close()
        return chapter_found, intro_found

    def add_result_row(self, book_name, url, category, title="", name="", attr="", source_id=None):
        chk_item = QStandardItem()
        chk_item.setCheckable(True)
        chk_item.setCheckState(Qt.Checked)
        chk_item.setData({"url": url, "cat": category, "book_name": book_name, "source_id": source_id},
                         Qt.UserRole)

        col_book = QStandardItem(book_name or "未关联")
        col_url = QStandardItem(url)
        col_cat = QStandardItem(category)

        display_name = name if name else ""
        col_name = QStandardItem(display_name)

        col_attr = QStandardItem(attr)

        self.result_model.appendRow([chk_item, col_book, col_url, col_cat, col_name, col_attr])

    def save_results(self):
        # ★ 逻辑层拦截
        if license_mgr.is_expired:
            QMessageBox.warning(self, "功能受限", "您的会员已过期，无法将抓取结果保存到库中。")
            return

        rows_to_save = []
        for row in range(self.result_model.rowCount()):
            chk_item = self.result_model.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.Checked:
                data = chk_item.data(Qt.UserRole)
                if not data:
                    continue
                data["name"] = self.result_model.item(row, 4).text().strip()
                data["attr"] = self.result_model.item(row, 5).text().strip()
                rows_to_save.append(data)

        if not rows_to_save:
            QMessageBox.warning(self, "提示", "没有勾选任何有效数据！")
            return

        conn = get_conn()
        cursor = conn.cursor()
        saved_count = 0
        duplicate_count = 0
        source_ids_to_mark = set()

        for item_data in rows_to_save:
            url = item_data["url"]
            cat = item_data["cat"]
            book_name = item_data["book_name"]
            name = item_data.get("name", "")
            attr = item_data.get("attr", "")
            source_id = item_data.get("source_id")

            if source_id:
                source_ids_to_mark.add(source_id)

            book_id = None
            if book_name:
                res = cursor.execute("SELECT id FROM books WHERE name=?", (book_name,)).fetchone()
                if res:
                    book_id = res[0]

            code = extract_pure_feature(url)
            if cursor.execute("SELECT id FROM sites WHERE feature_code=?", (code,)).fetchone():
                duplicate_count += 1
                continue

            try:
                # ★ category 与 target_platform 双写，确保在盗版链接页正常显示分类。
                #   page_links.refresh_table() 的资源分类列读的就是 target_platform。
                cursor.execute('''INSERT INTO sites
                                  (category, target_platform, site_url, feature_code, book_id, book_name, name, attr, crawl_status)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (cat, cat, url, code, book_id, book_name, name, attr, '已抓取'))
                saved_count += 1
            except sqlite3.IntegrityError:
                pass

        for s_id in source_ids_to_mark:
            cursor.execute("UPDATE sites SET crawl_status='已抓取' WHERE id=?", (s_id,))

        conn.commit()
        conn.close()

        self.result_model.removeRows(0, self.result_model.rowCount())
        self.refresh_data()

        QMessageBox.information(self, "保存成功", f"已向库中新增 {saved_count} 条记录！\n跳过重复 {duplicate_count} 条。")

        if hasattr(self.main_window, 'links_page'):
            self.main_window.links_page.refresh_table()