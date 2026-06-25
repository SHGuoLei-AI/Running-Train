import json
import os
import shutil
import sqlite3
import locale
from datetime import datetime
from PySide6.QtWidgets import (QMainWindow, QMessageBox, QWidget, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLineEdit, QFileDialog, QScrollArea, QSplitter,
                               QInputDialog, QListWidget, QListWidgetItem, QDialog,
                               QDialogButtonBox, QAbstractItemView)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from models import (TrainGraph, RailwayPath, RailwayTrack,
                    load_train_graph_from_json, save_train_graph_to_json,
                    load_train_graph_from_db, save_train_graph_to_db,
                    list_graphs_in_db)
from canvas import DrawingCanvas
from delegates import RadioDelegate
from simulation import TrainPositioner, SimulationClock
from sim_controls import SimulationControlPanel
import config

locale.setlocale(locale.LC_COLLATE, 'chs')  # pinyin sort for Chinese

KL_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kl.db')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._refreshing = False
        self._current_graph_name = None

        # 模拟状态
        self._sim_clock: SimulationClock | None = None
        self._sim_panel: SimulationControlPanel | None = None
        self._positioner: TrainPositioner | None = None

        # DB connection (persistent, shared across app lifetime)
        db_path = config.get_rg_path()
        self._db = sqlite3.connect(db_path)
        self.setWindowTitle(f"Running Train — {config.get_active_graph().get('name', '')}")

        # 手动创建主窗口部件
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(2)
        self.canvas_widget = QWidget()
        central_layout.addWidget(self.canvas_widget, stretch=1)

        # 菜单栏
        self.menu_file = self.menuBar().addMenu("文件(&F)")
        self.menu_graph = self.menuBar().addMenu("图(&G)")
        self.menu_routes = self.menuBar().addMenu("经由(&R)")
        self.menu_tools = self.menuBar().addMenu("工具(&T)")
        self.menu_settings = self.menuBar().addMenu("设置(&S)")
        self.menu_help = self.menuBar().addMenu("帮助(&H)")

        # 图菜单：切换激活图
        self._graph_actions = {}
        self._build_graph_menu()
        self.action_exit = self.menu_file.addAction("退出")
        self.action_route_editor = self.menu_routes.addAction("经由维护...")
        self.menu_routes.addSeparator()
        self.action_route_match = self.menu_routes.addAction("车次匹配...")
        self.menu_routes.addSeparator()
        self.action_route_matched_trains = self.menu_routes.addAction("经由匹配的车次")
        self.action_train_matched_routes = self.menu_routes.addAction("车次匹配的经由")
        self.action_update_schedule = self.menu_tools.addAction("更新时刻表...")
        self.action_update_kl = self.menu_tools.addAction("更新里程表...")
        self.action_auto_backup = QAction("自动备份", self)
        self.action_auto_backup.setCheckable(True)
        self.action_auto_backup.setChecked(self._get_auto_backup())
        self.menu_settings.addAction(self.action_auto_backup)
        self.action_delete_backups = self.menu_settings.addAction("删除备份文件...")
        self.action_about = self.menu_help.addAction("关于")

        # 文件菜单：打开、保存、另存为、导入/导出 JSON
        self.action_open = self.menu_file.addAction("打开(&O)...")
        self.action_open.triggered.connect(self.on_open_clicked)
        self.action_save = self.menu_file.addAction("保存(&S)")
        self.action_save.triggered.connect(self.on_save_clicked)
        self.action_save_as = self.menu_file.addAction("另存为(&A)...")
        self.action_save_as.triggered.connect(self.on_save_as_clicked)
        self.menu_file.addSeparator()
        self.action_import_json = self.menu_file.addAction("导入 JSON...")
        self.action_import_json.triggered.connect(self.on_import_json_clicked)
        self.action_export_json = self.menu_file.addAction("导出 JSON...")
        self.action_export_json.triggered.connect(self.on_export_json_clicked)
        self.menu_file.insertSeparator(self.action_exit)

        # 图切换信号连接
        self.action_exit.triggered.connect(self.close)

        # 默认从 DB 加载
        self._load_from_db()

        # 自动备份（如果开启）
        if self._get_auto_backup():
            self._do_backup()

        self.graph_name_field = QLineEdit(self.train_graph.name)
        self.graph_name_field.setStyleSheet("font-size: 12px; font-weight: bold; border: 1px solid #ccc;")
        self.graph_name_field.editingFinished.connect(self.on_graph_params_changed)
        self.graph_length_field = QLineEdit(str(self.train_graph.length))
        self.graph_length_field.setFixedWidth(40)
        self.graph_length_field.editingFinished.connect(self.on_graph_params_changed)
        self.graph_width_field = QLineEdit(str(self.train_graph.width))
        self.graph_width_field.setFixedWidth(40)
        self.graph_width_field.editingFinished.connect(self.on_graph_params_changed)
        self.graph_scale_field = QLineEdit(str(self.train_graph.scale))
        self.graph_scale_field.setFixedWidth(30)
        self.graph_scale_field.editingFinished.connect(self.on_graph_params_changed)

        self.graph_param_layout = QHBoxLayout()
        self.graph_param_layout.setContentsMargins(0, 0, 0, 0)
        self.graph_param_layout.setSpacing(2)
        name_label = QLabel("名称:"); name_label.setStyleSheet("border: none;")
        len_label = QLabel("长:"); len_label.setStyleSheet("border: none;")
        wid_label = QLabel("宽:"); wid_label.setStyleSheet("border: none;")
        scl_label = QLabel("比例尺:"); scl_label.setStyleSheet("border: none;")
        self.graph_param_layout.addWidget(name_label)
        self.graph_param_layout.addWidget(self.graph_name_field, stretch=1)
        self.graph_param_layout.addWidget(len_label)
        self.graph_param_layout.addWidget(self.graph_length_field)
        self.graph_param_layout.addWidget(wid_label)
        self.graph_param_layout.addWidget(self.graph_width_field)
        self.graph_param_layout.addWidget(scl_label)
        self.graph_param_layout.addWidget(self.graph_scale_field)

        self.train_path_table = QTableWidget()
        self.train_path_table.setColumnCount(9)
        self.train_path_table.setHorizontalHeaderLabels(
            ["隐", "线路", "线路正式名", "X", "Y", "角度", "首站", "末站", "长度"])
        widths = [20, 65, 145, 40, 40, 40, 80, 80, 40]
        for i, w in enumerate(widths):
            self.train_path_table.setColumnWidth(i, w)
        self.train_path_table.verticalHeader().setFixedWidth(24)
        self.train_path_table.itemSelectionChanged.connect(self.on_train_path_selected)
        self.train_path_table.itemChanged.connect(self.on_path_item_changed)
        self.train_path_table.cellClicked.connect(self.on_path_table_cell_clicked)

        self.path_selected_label = QLabel("")
        self.path_selected_label.setStyleSheet("font-weight: bold; border: none;")

        self.path_btn_layout = QHBoxLayout()
        self.path_btn_layout.setContentsMargins(0, 0, 0, 0)
        self.add_path_from_kl_button = QPushButton("  从客里表新增  ")
        self.add_path_from_kl_button.clicked.connect(self.on_add_path_from_kl_clicked)
        self.add_path_button = QPushButton("  新增线路  ")
        self.add_path_button.clicked.connect(self.on_add_path_clicked)
        self.delete_path_button = QPushButton("  删除线路  ")
        self.delete_path_button.clicked.connect(self.on_delete_path_clicked)
        self.move_up_button = QPushButton("  上移  ")
        self.move_up_button.clicked.connect(self.on_move_path_up_clicked)
        self.move_down_button = QPushButton("  下移  ")
        self.move_down_button.clicked.connect(self.on_move_path_down_clicked)
        self.path_btn_layout.addWidget(self.path_selected_label)
        self.path_btn_layout.addStretch()
        self.path_btn_layout.addWidget(self.move_up_button)
        self.path_btn_layout.addWidget(self.move_down_button)
        self.path_btn_layout.addWidget(self.add_path_from_kl_button)
        self.path_btn_layout.addWidget(self.add_path_button)
        self.path_btn_layout.addWidget(self.delete_path_button)

        self.rail_track_table = QTableWidget()
        self.rail_track_table.setColumnCount(8)
        self.rail_track_table.setHorizontalHeaderLabels(
            ["画", "头站", "画", "尾站", "长度", "偏转", "上行方向", "下行方向"])
        widths = [20, 80, 20, 80, 40, 30, 56, 56]
        for i, w in enumerate(widths):
            self.rail_track_table.setColumnWidth(i, w)
        self.rail_track_table.verticalHeader().setFixedWidth(24)
        self.rail_track_table.itemChanged.connect(self.on_track_item_changed)
        self.rail_track_table.cellClicked.connect(self.on_track_table_cell_clicked)

        self._radio_delegate = RadioDelegate()
        self.train_path_table.setItemDelegateForColumn(0, self._radio_delegate)
        self.rail_track_table.setItemDelegateForColumn(0, self._radio_delegate)
        self.rail_track_table.setItemDelegateForColumn(2, self._radio_delegate)

        self.track_btn_layout = QHBoxLayout()
        self.track_btn_layout.setContentsMargins(0, 0, 0, 0)
        self.extend_head_button = QPushButton("  头部延伸  ")
        self.extend_head_button.clicked.connect(self.on_extend_head_clicked)
        self.insert_track_button = QPushButton("  插入区间  ")
        self.insert_track_button.clicked.connect(self.on_insert_track_clicked)
        self.extend_tail_button = QPushButton("  尾部延伸  ")
        self.extend_tail_button.clicked.connect(self.on_add_track_clicked)
        self.delete_track_button = QPushButton("  删除区间  ")
        self.delete_track_button.clicked.connect(self.on_delete_track_clicked)
        self.track_btn_layout.addStretch()
        self.track_btn_layout.addWidget(self.extend_head_button)
        self.track_btn_layout.addWidget(self.insert_track_button)
        self.track_btn_layout.addWidget(self.extend_tail_button)
        self.track_btn_layout.addWidget(self.delete_track_button)

        self.data_panel = QWidget()
        data_layout = QVBoxLayout(self.data_panel)
        data_layout.setContentsMargins(2, 2, 2, 2)
        data_layout.setSpacing(2)
        data_layout.addLayout(self.graph_param_layout)
        data_layout.addWidget(self.train_path_table, stretch=1)
        data_layout.addLayout(self.path_btn_layout)
        data_layout.addWidget(self.rail_track_table, stretch=1)
        data_layout.addLayout(self.track_btn_layout)

        self._original_scale = self.train_graph.scale
        self.scale_plus_btn = QPushButton(" + ")
        self.scale_plus_btn.clicked.connect(self.on_scale_plus_clicked)
        self.scale_reset_btn = QPushButton(" # ")
        self.scale_reset_btn.clicked.connect(self.on_scale_reset_clicked)
        self.scale_minus_btn = QPushButton(" - ")
        self.scale_minus_btn.clicked.connect(self.on_scale_minus_clicked)
        self.toggle_panel_btn = QPushButton(" ▸ ")
        self.toggle_panel_btn.setToolTip("显示/隐藏数据面板")
        self.toggle_panel_btn.clicked.connect(self.on_toggle_panel_clicked)
        scale_btn_row = QHBoxLayout()
        scale_btn_row.setContentsMargins(0, 0, 0, 0)
        scale_btn_row.addStretch()
        scale_btn_row.addWidget(self.scale_plus_btn)
        scale_btn_row.addWidget(self.scale_reset_btn)
        scale_btn_row.addWidget(self.scale_minus_btn)
        scale_btn_row.addWidget(self.toggle_panel_btn)

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setWidget(self.canvas)

        left_panel = QVBoxLayout()
        left_panel.setContentsMargins(0, 0, 0, 0)
        left_panel.setSpacing(2)
        left_panel.addWidget(self.scroll_area, stretch=1)
        left_panel.addLayout(scale_btn_row)

        left_container = QWidget()
        left_container.setLayout(left_panel)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(left_container)
        self._splitter.addWidget(self.data_panel)
        self._splitter.setCollapsible(1, False)
        self.data_panel.setMinimumWidth(50)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)

        canvas_layout = self.canvas_widget.layout() or QHBoxLayout(self.canvas_widget)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        while canvas_layout.count():
            canvas_layout.takeAt(0)

        # 模拟控制面板（左侧，100px 宽，启动即显示）
        self._sim_panel = SimulationControlPanel()
        canvas_layout.addWidget(self._sim_panel)

        canvas_layout.addWidget(self._splitter, stretch=1)

        # 模拟时钟
        self._sim_clock = SimulationClock(self)

        self.refresh_train_path_table()
        self.update_graph_param_fields()
        self.connect_signals()

        # 启动模拟（以系统当前时间）
        self._init_simulation()

    # ── 菜单 & 信号 ──────────────────────────────────────

    def connect_signals(self):
        self.action_exit.triggered.connect(self.close)
        self.action_about.triggered.connect(self.on_about_clicked)
        self.action_route_editor.triggered.connect(self.on_route_editor_clicked)
        self.action_route_match.triggered.connect(self.on_route_match_clicked)
        self.action_route_matched_trains.triggered.connect(self.on_route_matched_trains_clicked)
        self.action_train_matched_routes.triggered.connect(self.on_train_matched_routes_clicked)
        self.action_update_schedule.triggered.connect(self.on_update_schedule_clicked)
        self.action_update_kl.triggered.connect(self.on_update_kl_clicked)
        self.action_auto_backup.triggered.connect(self.on_auto_backup_toggled)
        self.action_delete_backups.triggered.connect(self.on_delete_backups_clicked)

        # 控制面板 → 时钟
        self._sim_panel.start_clicked.connect(self._on_start)
        self._sim_panel.pause_clicked.connect(self._on_pause)
        self._sim_panel.hour_clicked.connect(self._sim_clock.jump_to)
        self._sim_panel.speed_changed.connect(self._sim_clock.set_speed)
        self._sim_panel.step_minute.connect(self._sim_clock.step)

        # 时钟 → UI
        self._sim_clock.time_changed.connect(self._on_sim_tick)

    def _on_start(self):
        self._sim_clock.start()
        self._sim_panel.set_running(True)

    def _on_pause(self):
        self._sim_clock.pause()
        self._sim_panel.set_running(False)

    def on_update_schedule_clicked(self):
        QMessageBox.information(self, "更新时刻表",
            "从路路通 APK 提取时刻表数据写入 cc.db。\n\n"
            "雏形脚本: tools/parse_llt_apk.py\n"
            "待完善：集成到 GUI，显示进度，自动备份旧版本。")

    def on_update_kl_clicked(self):
        QMessageBox.information(self, "更新里程表",
            "从 jprailfan.com/tools/stat/ 获取最新客里表数据写入 kl.db。\n\n"
            "待完善：实现下载解析逻辑。")

    # ── 备份 ──────────────────────────────────────────

    @property
    def _backup_dir(self):
        d = os.path.join(os.path.dirname(__file__), 'data', 'backup')
        os.makedirs(d, exist_ok=True)
        return d

    def _get_auto_backup(self):
        try:
            row = self._db.execute(
                "SELECT value FROM meta WHERE key='auto_backup'").fetchone()
            if row is None:
                # 首次使用默认开启
                self._set_auto_backup(True)
                return True
            return row[0] == '1'
        except Exception:
            return True  # 出错时也默认开启

    def _set_auto_backup(self, enabled):
        self._db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('auto_backup', ?)",
            ('1' if enabled else '0',))
        self._db.commit()

    def _do_backup(self):
        """Copy all DBs to backup dir with timestamp."""
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        # Common DBs
        for name in ['kl.db', 'cc.db']:
            src = os.path.join(data_dir, name)
            if os.path.exists(src):
                dst = os.path.join(self._backup_dir, f'{name}_{ts}')
                shutil.copy2(src, dst)
        # Graph-specific DBs
        for g in config.load_graphs().get('graphs', []):
            for key in ('rg_db', 'rt_db'):
                rpath = g.get(key, '')
                src = os.path.join(os.path.dirname(__file__), rpath) if not os.path.isabs(rpath) else rpath
                if os.path.exists(src):
                    basename = os.path.basename(src)
                    dst = os.path.join(self._backup_dir, f'{basename}_{ts}')
                    shutil.copy2(src, dst)
        # Clean old backups: keep last 20 versions
        all_bak = sorted(os.listdir(self._backup_dir))
        while len(all_bak) > 80:  # 4 DBs × 20 versions
            for f in all_bak[:4]:
                os.remove(os.path.join(self._backup_dir, f))
            all_bak = all_bak[4:]

    def on_auto_backup_toggled(self, checked):
        self._set_auto_backup(checked)

    # ── 图切换 ──────────────────────────────────────────

    def _build_graph_menu(self):
        """构建图切换菜单（radio-action 样式）。"""
        self.menu_graph.clear()
        self._graph_actions.clear()
        graphs = config.load_graphs().get('graphs', [])
        active_id = config.load_graphs().get('active', '')
        for g in graphs:
            action = self.menu_graph.addAction(g['name'])
            action.setCheckable(True)
            if g['id'] == active_id:
                action.setChecked(True)
            action.triggered.connect(lambda checked, gid=g['id']: self._on_switch_graph(gid))
            self._graph_actions[g['id']] = action

    def _on_switch_graph(self, graph_id: str):
        """切换激活图并重新加载。"""
        if graph_id == config.load_graphs().get('active', ''):
            return
        config.set_active_graph(graph_id)
        # 关闭旧连接，打开新连接
        if hasattr(self, '_db') and self._db:
            self._db.close()
        db_path = config.get_rg_path()
        self._db = sqlite3.connect(db_path)
        self.setWindowTitle(f"Running Train — {config.get_active_graph().get('name', '')}")
        # 重新加载
        self._load_from_db()
        # 重建模拟
        self._refresh_simulation()
        self._build_graph_menu()

    def on_delete_backups_clicked(self):
        """Dialog to select and delete backup files."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox, QAbstractItemView
        dlg = QDialog(self)
        dlg.setWindowTitle("删除备份文件")
        dlg.resize(500, 400)
        layout = QVBoxLayout(dlg)

        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        files = sorted(os.listdir(self._backup_dir), reverse=True)
        for f in files:
            lst.addItem(f)
        layout.addWidget(lst)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = [item.text() for item in lst.selectedItems()]
            if not selected:
                return
            reply = QMessageBox.question(self, "确认删除",
                f"确定要删除 {len(selected)} 个备份文件吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                for f in selected:
                    os.remove(os.path.join(self._backup_dir, f))
                QMessageBox.information(self, "完成", f"已删除 {len(selected)} 个备份文件。")

    # ── About ──────────────────────────────────────────

    def on_about_clicked(self):
        QMessageBox.about(self, "关于", "欢迎使用动态模拟火车运行图")

    def on_route_editor_clicked(self):
        from route_editor import RouteEditorDialog
        dlg = RouteEditorDialog(self)
        dlg.exec()

    def on_route_match_clicked(self):
        """Run matching engine directly from menu (same as the button in route editor)."""
        from tools.match_trains import run_matching_with_progress
        cc_path = os.path.join(os.path.dirname(__file__), 'data', 'cc.db')
        rt_path = config.get_rt_path()
        run_matching_with_progress(self, self._db, cc_path, rt_path)

    def on_route_matched_trains_clicked(self):
        from train_match_dialogs import RouteMatchTrainsDialog
        dlg = RouteMatchTrainsDialog(self)
        dlg.exec()

    def on_train_matched_routes_clicked(self):
        from train_match_dialogs import TrainMatchRoutesDialog
        dlg = TrainMatchRoutesDialog(self)
        dlg.exec()

    _panel_last_width = 300

    def init_splitter_sizes(self):
        w = self.width()
        self._splitter.setSizes([w - 600, 600])

    def on_toggle_panel_clicked(self):
        visible = self.data_panel.isVisible()
        if visible:
            sizes = self._splitter.sizes()
            if sizes[1] > 0:
                self._panel_last_width = sizes[1]
            self.data_panel.setVisible(False)
            self.toggle_panel_btn.setText(" ◂ ")
        else:
            self.data_panel.setVisible(True)
            total = sum(self._splitter.sizes())
            w = max(self._panel_last_width, 150)
            self._splitter.setSizes([total - w, w])
            self.toggle_panel_btn.setText(" ▸ ")

    # ── 缩放按钮 ─────────────────────────────────────────

    def on_scale_plus_clicked(self):
        if self.train_graph.scale < 10:
            self.train_graph.scale += 1
            self.canvas._update_size()
            self.update_graph_param_fields()
            self.canvas.update()
            self._refresh_simulation()

    def on_scale_reset_clicked(self):
        self.train_graph.scale = self._original_scale
        self.canvas._update_size()
        self.update_graph_param_fields()
        self.canvas.update()
        self._refresh_simulation()

    def on_scale_minus_clicked(self):
        if self.train_graph.scale > 1:
            self.train_graph.scale -= 1
            self.canvas._update_size()
            self.update_graph_param_fields()
            self.canvas.update()
            self._refresh_simulation()

    # ── DB I/O ──────────────────────────────────────────

    def _load_from_db(self, graph_name=None):
        self.train_graph = load_train_graph_from_db(self._db)  # graph_name no longer used
        self._current_graph_name = self.train_graph.name
        self._original_scale = self.train_graph.scale
        self.canvas = DrawingCanvas(self.train_graph)
        if hasattr(self, 'scroll_area'):
            self.scroll_area.setWidget(self.canvas)

    def on_open_clicked(self):
        """Switch to a different graph in the DB."""
        graphs = list_graphs_in_db(self._db)
        if not graphs:
            QMessageBox.information(self, "提示", "数据库中没有运行图。可使用 文件→导入 JSON 导入。")
            return
        names = [g[0] for g in graphs]
        if len(names) == 1:
            QMessageBox.information(self, "提示", f"数据库中只有一份运行图：{names[0]}")
            return
        name, ok = QInputDialog.getItem(self, "打开运行图", "选择运行图:", names, 0, False)
        if ok and name and name != self._current_graph_name:
            self._load_from_db(name)
            self.refresh_train_path_table()
            self.update_graph_param_fields()
            self.path_selected_label.setText("")
            self.rail_track_table.setRowCount(0)
            self.canvas.update()

    def on_save_clicked(self):
        save_train_graph_to_db(self.train_graph, self._db)
        self._current_graph_name = self.train_graph.name

    def on_save_as_clicked(self):
        """Save current graph under a new name in the DB."""
        name, ok = QInputDialog.getText(
            self, "另存为", "新运行图名称:",
            text=self.train_graph.name + " (副本)")
        if ok and name:
            old_name = self.train_graph.name
            self.train_graph.name = name
            try:
                save_train_graph_to_db(self.train_graph, self._db)
                self._current_graph_name = name
                self.update_graph_param_fields()
            except Exception:
                self.train_graph.name = old_name
                raise

    def on_import_json_clicked(self):
        """Import a JSON file into the DB (graph + optional routes)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入 JSON 运行图",
            os.path.join(os.path.dirname(__file__), 'data'),
            "JSON 文件 (*.json);;所有文件 (*)")
        if not file_path:
            return
        train_graph = load_train_graph_from_json(file_path)
        # Check if name already exists in DB
        existing = self._db.execute(
            'SELECT 1 FROM train_graph WHERE name=?', (train_graph.name,)).fetchone()
        if existing:
            reply = QMessageBox.question(
                self, "覆盖确认",
                f"数据库中已存在运行图「{train_graph.name}」，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        save_train_graph_to_db(train_graph, self._db)

        # Import routes if present in JSON
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        g = data.get('TrainGraph', data)
        routes_data = g.get('routes', [])
        route_stations_data = g.get('route_stations', [])
        if routes_data:
            # Clear existing routes and re-insert
            self._db.execute('DELETE FROM route_stations')
            self._db.execute('DELETE FROM routes')
            for r in routes_data:
                self._db.execute(
                    'INSERT INTO routes (id, name, start_station, end_station, '
                    'total_distance, prohibit_high_speed, prohibit_normal_speed) '
                    'VALUES (?,?,?,?,?,?,?)',
                    (r['id'], r['name'], r['start_station'], r['end_station'],
                     r['total_distance'],
                     1 if r.get('prohibit_high_speed') else 0,
                     1 if r.get('prohibit_normal_speed') else 0))
            for s in route_stations_data:
                self._db.execute(
                    'INSERT INTO route_stations '
                    '(route_id, seq, station_name, line_name, cum_distance, is_junction) '
                    'VALUES (?,?,?,?,?,?)',
                    (s['route_id'], s['seq'], s['station_name'], s['line_name'],
                     s['cum_distance'], 1 if s.get('is_junction') else 0))
            self._db.commit()

        self._load_from_db(train_graph.name)
        self.refresh_train_path_table()
        self.update_graph_param_fields()
        self.path_selected_label.setText("")
        self.rail_track_table.setRowCount(0)
        self.canvas.update()
        msg = f"成功导入「{train_graph.name}」：{len(train_graph.train_paths)} 条线路"
        if routes_data:
            msg += f", {len(routes_data)} 条经由"
        QMessageBox.information(self, "导入完成", msg)

    def on_export_json_clicked(self):
        """Export current graph + routes to a JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出 JSON 运行图",
            os.path.join(os.path.dirname(__file__), 'data',
                         f'{self.train_graph.name}.json'),
            "JSON 文件 (*.json);;所有文件 (*)")
        if not file_path:
            return
        # Read routes from DB
        route_rows = self._db.execute(
            'SELECT id, name, start_station, end_station, total_distance, '
            'prohibit_high_speed, prohibit_normal_speed '
            'FROM routes ORDER BY id').fetchall()
        routes = [
            {
                "id": r[0], "name": r[1],
                "start_station": r[2], "end_station": r[3],
                "total_distance": r[4],
                "prohibit_high_speed": bool(r[5]),
                "prohibit_normal_speed": bool(r[6]),
            }
            for r in route_rows
        ]
        # Read route_stations
        st_rows = self._db.execute(
            'SELECT route_id, seq, station_name, line_name, cum_distance, is_junction '
            'FROM route_stations ORDER BY route_id, seq').fetchall()
        route_stations = [
            {
                "route_id": r[0], "seq": r[1],
                "station_name": r[2], "line_name": r[3],
                "cum_distance": r[4], "is_junction": bool(r[5]),
            }
            for r in st_rows
        ]
        save_train_graph_to_json(self.train_graph, file_path,
                                 routes=routes, route_stations=route_stations)
        QMessageBox.information(self, "导出完成",
            f"已导出到 {file_path}\n"
            f"{len(self.train_graph.train_paths)} 条线路, {len(routes)} 条经由")

    # ── 图表参数编辑 ─────────────────────────────────────

    def update_graph_param_fields(self):
        self.graph_name_field.setText(self.train_graph.name)
        self.graph_length_field.setText(str(int(self.train_graph.length)))
        self.graph_width_field.setText(str(int(self.train_graph.width)))
        self.graph_scale_field.setText(str(int(self.train_graph.scale)))

    def on_graph_params_changed(self):
        try:
            self.train_graph.name = self.graph_name_field.text().strip()
            self.train_graph.length = int(float(self.graph_length_field.text().strip()))
            self.train_graph.width = int(float(self.graph_width_field.text().strip()))
            self.train_graph.scale = int(float(self.graph_scale_field.text().strip()))
        except ValueError:
            pass
        self.update_graph_param_fields()
        self.canvas._update_size()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)

    # ── 线路表 ────────────────────────────────────────────

    def refresh_train_path_table(self):
        self.train_path_table.blockSignals(True)
        n = len(self.train_graph.train_paths)
        self._sync_table_rows(self.train_path_table, n)
        for i, path in enumerate(self.train_graph.train_paths):
            self._set_path_row(i, path)
        self.train_path_table.blockSignals(False)

    def _set_path_row(self, row, path):
        # Col 0: hidden checkbox
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsEnabled)
        chk.setData(Qt.ItemDataRole.CheckStateRole,
                    Qt.CheckState.Checked if path.hidden else Qt.CheckState.Unchecked)
        self.train_path_table.setItem(row, 0, chk)
        # Col 1: name
        self.train_path_table.setItem(row, 1, QTableWidgetItem(path.name))
        # Col 2: kl_line_name
        kl = getattr(path, 'kl_line_name', '') or ''
        self.train_path_table.setItem(row, 2, QTableWidgetItem(kl))
        # Col 3-5: X, Y, angle
        self.train_path_table.setItem(row, 3, QTableWidgetItem(str(int(path.start_point[0]))))
        self.train_path_table.setItem(row, 4, QTableWidgetItem(str(int(path.start_point[1]))))
        self.train_path_table.setItem(row, 5, QTableWidgetItem(str(int(path.angle))))
        # Col 6-8: computed
        self.train_path_table.setItem(row, 6, QTableWidgetItem(path.get_first_station() or ""))
        self.train_path_table.setItem(row, 7, QTableWidgetItem(path.get_last_station() or ""))
        self.train_path_table.setItem(row, 8, QTableWidgetItem(str(path.get_length())))

    def on_path_item_changed(self, item):
        if self._refreshing:
            return
        row = item.row()
        col = item.column()
        if row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[row]
        needs_sim_refresh = False
        try:
            if col == 0:  # hidden (cosmetic)
                path.hidden = (item.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked)
            elif col == 1:  # name (cosmetic)
                path.name = item.text().strip()
            elif col == 2:  # kl_line_name (cosmetic)
                path.kl_line_name = item.text().strip()
            elif col == 3:  # X (geometry)
                x = int(float(item.text().strip()))
                path.start_point = (x, path.start_point[1])
                self._update_track_positions(path)
                needs_sim_refresh = True
            elif col == 4:  # Y (geometry)
                y = int(float(item.text().strip()))
                path.start_point = (path.start_point[0], y)
                self._update_track_positions(path)
                needs_sim_refresh = True
            elif col == 5:  # angle (geometry)
                path.angle = int(float(item.text().strip()))
                self._update_track_positions(path)
                needs_sim_refresh = True
        except ValueError:
            pass
        self.canvas._update_size()
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        if needs_sim_refresh:
            self._refresh_simulation()

    def on_path_table_cell_clicked(self, row, col):
        if col != 0:
            return
        item = self.train_path_table.item(row, col)
        if not item:
            return
        current = item.data(Qt.ItemDataRole.CheckStateRole)
        new_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
        item.setData(Qt.ItemDataRole.CheckStateRole, new_state)

    def on_train_path_selected(self):
        row = self.train_path_table.currentRow()
        if 0 <= row < len(self.train_graph.train_paths):
            path = self.train_graph.train_paths[row]
            self.path_selected_label.setText(path.name)
            self.refresh_rail_track_table(row)

    def on_add_path_from_kl_clicked(self):
        """从客里表选择线路和首末站，新增线路（逐站生成区间）。"""
        result = self._pick_kl_path_segment()
        if result is None:
            return

        line_name, first_station, last_station = result

        # 查kl获取首末站之间的所有车站（按里程排序）
        kl = sqlite3.connect(KL_PATH)
        try:
            all_sts = kl.execute(
                "SELECT station_name, dist_from_start FROM line_stations "
                "WHERE line_name=? ORDER BY dist_from_start",
                (line_name,)
            ).fetchall()
            fd = kl.execute(
                "SELECT dist_from_start FROM line_stations WHERE line_name=? AND station_name=?",
                (line_name, first_station)).fetchone()
            ed = kl.execute(
                "SELECT dist_from_start FROM line_stations WHERE line_name=? AND station_name=?",
                (line_name, last_station)).fetchone()
        finally:
            kl.close()

        if fd is None or ed is None:
            return

        f_dist = fd[0]
        e_dist = ed[0]
        forward = f_dist <= e_dist  # 正向：首站里程 ≤ 末站里程

        # 筛选首末站之间的车站（含首末站），按方向排序
        if forward:
            stations = [(sn, d) for sn, d in all_sts if f_dist <= d <= e_dist]
        else:
            stations = [(sn, d) for sn, d in all_sts if e_dist <= d <= f_dist]
            stations = list(reversed(stations))

        if len(stations) < 2:
            return

        new_id = f"P{len(self.train_graph.train_paths) + 1}"
        path = RailwayPath(new_id, line_name, 50, 50, angle=0, hidden=False,
                           kl_line_name=line_name)

        # 逐站生成区间（相邻两站一个 track）
        for i in range(len(stations) - 1):
            sn_a, da = stations[i]
            sn_b, db = stations[i + 1]
            seg_len = int(abs(db - da))
            is_first = (i == 0)
            is_last = (i == len(stations) - 2)
            path.add_track(RailwayTrack(
                length=seg_len, deflection=0,
                head_station=sn_a, tail_station=sn_b,
                draw_head=is_first, draw_tail=is_last))

        self.train_graph.add_train_path(path)
        new_row = len(self.train_graph.train_paths) - 1
        self.train_path_table.blockSignals(True)
        self.train_path_table.insertRow(new_row)
        self._set_path_row(new_row, path)
        self.train_path_table.blockSignals(False)
        self.train_path_table.setCurrentCell(new_row, 1)
        self.train_path_table.scrollToItem(self.train_path_table.item(new_row, 1))
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        self._refresh_simulation()

    def _pick_kl_path_segment(self):
        """弹窗：从客里表选线路 → 首站 → 末站（同线路）。
        返回 (line_name, first_station, last_station) 或 None。"""
        kl = sqlite3.connect(KL_PATH)
        try:
            lines = kl.execute(
                "SELECT DISTINCT line_name FROM line_stations"
            ).fetchall()
            lines = sorted(lines, key=lambda x: locale.strxfrm(x[0]))
        finally:
            kl.close()

        dlg = QDialog(self)
        dlg.setWindowTitle("从客里表新增线路")
        dlg.resize(520, 520)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("注意：首站至末站需为下行方向！"))

        layout.addWidget(QLabel("选择线路:"))

        line_list = QListWidget()
        for (ln,) in lines:
            QListWidgetItem(ln, line_list)
        layout.addWidget(line_list)

        layout.addWidget(QLabel("选择首站:"))

        first_list = QListWidget()
        layout.addWidget(first_list)

        layout.addWidget(QLabel("选择末站:"))

        last_list = QListWidget()
        layout.addWidget(last_list)

        # Shared mutable state
        state = {'all_sts': [], 'first_idx': None, '_updating': False}

        def update_stations():
            first_list.clear()
            last_list.clear()
            state['all_sts'] = []
            state['first_idx'] = None

            if line_list.currentItem() is None:
                return
            ln = line_list.currentItem().text()

            kl2 = sqlite3.connect(KL_PATH)
            try:
                sts = kl2.execute(
                    "SELECT station_name, dist_from_start FROM line_stations "
                    "WHERE line_name=? ORDER BY dist_from_start",
                    (ln,)
                ).fetchall()
            finally:
                kl2.close()

            state['all_sts'] = sts
            for i, (sn, d) in enumerate(sts):
                QListWidgetItem(f"{sn}  ({d:.0f}km)", first_list)

        def on_first_changed(current, previous):
            if state['_updating'] or current is None:
                return
            first_idx = first_list.row(current)
            state['first_idx'] = first_idx

            last_list.clear()
            if first_idx < 0:
                return

            sts = state['all_sts']
            # 列出该线路全部车站（不限制方向，末站可能在首站之前）
            for i, (sn, d) in enumerate(sts):
                QListWidgetItem(f"{sn}  ({d:.0f}km)", last_list)

        line_list.currentItemChanged.connect(lambda: update_stations())

        def on_line_changed():
            update_stations()

        line_list.currentItemChanged.connect(lambda cur, prev: on_line_changed())
        first_list.currentItemChanged.connect(on_first_changed)

        if line_list.count() > 0:
            line_list.setCurrentRow(0)
            update_stations()

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        if (line_list.currentItem() is None or
                first_list.currentItem() is None or
                last_list.currentItem() is None):
            return None

        ln = line_list.currentItem().text()
        sn_text = first_list.currentItem().text()
        en_text = last_list.currentItem().text()
        first_stn = sn_text.split("  (")[0]
        last_stn = en_text.split("  (")[0]

        return (ln, first_stn, last_stn)

    def on_add_path_clicked(self):
        new_id = f"P{len(self.train_graph.train_paths) + 1}"
        path = RailwayPath(new_id, "新线路", 50, 50, angle=0, hidden=False)
        path.add_track(RailwayTrack(length=10, deflection=0, head_station="起点", tail_station="终点"))
        self.train_graph.add_train_path(path)
        new_row = len(self.train_graph.train_paths) - 1
        self.train_path_table.blockSignals(True)
        self.train_path_table.insertRow(new_row)
        self._set_path_row(new_row, path)
        self.train_path_table.blockSignals(False)
        self.train_path_table.setCurrentCell(new_row, 1)
        self.train_path_table.scrollToItem(self.train_path_table.item(new_row, 1))
        self.train_path_table.editItem(self.train_path_table.item(new_row, 1))
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        self._refresh_simulation()

    def on_delete_path_clicked(self):
        row = self.train_path_table.currentRow()
        if row < 0 or row >= len(self.train_graph.train_paths):
            return
        del self.train_graph.train_paths[row]
        self.refresh_train_path_table()
        self.path_selected_label.setText("")
        self.rail_track_table.setRowCount(0)
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        self._refresh_simulation()

    def on_move_path_up_clicked(self):
        row = self.train_path_table.currentRow()
        if row <= 0 or row >= len(self.train_graph.train_paths):
            return
        paths = self.train_graph.train_paths
        paths[row], paths[row - 1] = paths[row - 1], paths[row]
        self.train_path_table.blockSignals(True)
        self._set_path_row(row - 1, paths[row - 1])
        self._set_path_row(row, paths[row])
        self.train_path_table.blockSignals(False)
        self.train_path_table.setCurrentCell(row - 1, 1)
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)

    def on_move_path_down_clicked(self):
        row = self.train_path_table.currentRow()
        if row < 0 or row >= len(self.train_graph.train_paths) - 1:
            return
        paths = self.train_graph.train_paths
        paths[row], paths[row + 1] = paths[row + 1], paths[row]
        self.train_path_table.blockSignals(True)
        self._set_path_row(row, paths[row])
        self._set_path_row(row + 1, paths[row + 1])
        self.train_path_table.blockSignals(False)
        self.train_path_table.setCurrentCell(row + 1, 1)
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)

    # ── 区间表 ──────────────────────────────────────────

    def refresh_rail_track_table(self, idx):
        self.rail_track_table.blockSignals(True)
        path = self.train_graph.train_paths[idx]
        n = len(path.tracks)
        self._sync_table_rows(self.rail_track_table, n)
        for i, track in enumerate(path.tracks):
            self._set_track_row(i, track)
        self.rail_track_table.blockSignals(False)

    def _set_track_row(self, row, track):
        chkh = QTableWidgetItem()
        chkh.setFlags(Qt.ItemFlag.ItemIsEnabled)
        chkh.setData(Qt.ItemDataRole.CheckStateRole,
                     Qt.CheckState.Checked if track.draw_head else Qt.CheckState.Unchecked)
        self.rail_track_table.setItem(row, 0, chkh)
        self.rail_track_table.setItem(row, 1, QTableWidgetItem(track.head_station))
        chkt = QTableWidgetItem()
        chkt.setFlags(Qt.ItemFlag.ItemIsEnabled)
        chkt.setData(Qt.ItemDataRole.CheckStateRole,
                     Qt.CheckState.Checked if track.draw_tail else Qt.CheckState.Unchecked)
        self.rail_track_table.setItem(row, 2, chkt)
        self.rail_track_table.setItem(row, 3, QTableWidgetItem(track.tail_station))
        self.rail_track_table.setItem(row, 4, QTableWidgetItem(str(int(track.length))))
        self.rail_track_table.setItem(row, 5, QTableWidgetItem(str(int(track.deflection))))
        # 上行方向（点击循环切换）
        up_item = QTableWidgetItem(getattr(track, 'up_direction', 'N') or 'N')
        up_item.setFlags(up_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.rail_track_table.setItem(row, 6, up_item)
        # 下行方向（点击循环切换）
        down_item = QTableWidgetItem(getattr(track, 'down_direction', 'S') or 'S')
        down_item.setFlags(down_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.rail_track_table.setItem(row, 7, down_item)

    def on_track_item_changed(self, item):
        if self._refreshing:
            return
        row = item.row()
        col = item.column()
        sel_row = self.train_path_table.currentRow()
        if sel_row < 0 or sel_row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[sel_row]
        if row >= len(path.tracks):
            return
        track = path.tracks[row]
        needs_sim_refresh = False
        try:
            if col == 0:  # draw_head (cosmetic)
                track.draw_head = (item.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked)
            elif col == 1:  # head_station (station name → sim refresh)
                track.head_station = item.text().strip()
                needs_sim_refresh = True
            elif col == 2:  # draw_tail (cosmetic)
                track.draw_tail = (item.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked)
            elif col == 3:  # tail_station (station name → sim refresh)
                track.tail_station = item.text().strip()
                needs_sim_refresh = True
            elif col == 4:  # length (geometry → sim refresh)
                track.length = int(float(item.text().strip()))
                needs_sim_refresh = True
            elif col == 5:  # deflection (geometry → sim refresh)
                track.deflection = int(float(item.text().strip()))
                needs_sim_refresh = True

            if col in (4, 5):
                for i in range(row + 1, len(path.tracks)):
                    path.tracks[i].start_point = path.tracks[i - 1].end_point()
        except ValueError:
            pass
        self._update_path_computed_columns(sel_row)
        self.canvas._update_size()
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        if needs_sim_refresh:
            self._refresh_simulation()

    DIRECTION_CYCLE = ['N', 'E', 'S', 'W']

    def on_track_table_cell_clicked(self, row, col):
        if col in (0, 2):
            # 画头站/画尾站 checkbox
            item = self.rail_track_table.item(row, col)
            if not item:
                return
            current = item.data(Qt.ItemDataRole.CheckStateRole)
            new_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setData(Qt.ItemDataRole.CheckStateRole, new_state)
        elif col in (6, 7):
            # 上行/下行方向：点击循环切换
            item = self.rail_track_table.item(row, col)
            if not item:
                return
            current = item.text()
            try:
                idx = self.DIRECTION_CYCLE.index(current)
            except ValueError:
                idx = 0
            new_dir = self.DIRECTION_CYCLE[(idx + 1) % len(self.DIRECTION_CYCLE)]
            item.setText(new_dir)
            # 写入 track 对象
            sel_row = self.train_path_table.currentRow()
            if 0 <= sel_row < len(self.train_graph.train_paths):
                path = self.train_graph.train_paths[sel_row]
                if row < len(path.tracks):
                    track = path.tracks[row]
                    if col == 6:
                        track.up_direction = new_dir
                    else:
                        track.down_direction = new_dir
                    from models import save_train_graph_to_db
                    save_train_graph_to_db(self.train_graph, self._db)
                    self.canvas.update()
                    self._refresh_simulation()

    def on_extend_head_clicked(self):
        """在第一个区间前插入新区间（头部延伸）。"""
        sel_row = self.train_path_table.currentRow()
        if sel_row < 0 or sel_row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[sel_row]
        if not path.tracks:
            self.on_add_track_clicked()
            return

        old_head = path.tracks[0].head_station
        new_track = RailwayTrack(length=10, deflection=0, head_station="新头站", tail_station=old_head)
        path.tracks.insert(0, new_track)

        # 级联更新所有区间起点
        for i in range(len(path.tracks)):
            if i == 0:
                path.tracks[i].start_point = path.start_point
            else:
                path.tracks[i].start_point = path.tracks[i - 1].end_point()

        self.refresh_rail_track_table(sel_row)
        self.refresh_train_path_table()
        self.rail_track_table.setCurrentCell(0, 1)
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        self._refresh_simulation()

    def on_insert_track_clicked(self):
        sel_row = self.train_path_table.currentRow()
        if sel_row < 0 or sel_row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[sel_row]
        if not path.tracks:
            return

        track_row = self.rail_track_table.currentRow()
        if track_row < 0 or track_row >= len(path.tracks) - 1:
            # 选中的是最后一个或未选中，等同新增
            self.on_add_track_clicked()
            return

        nxt = path.tracks[track_row + 1]
        old_head = nxt.head_station
        nxt.head_station = "新站"

        new_track = RailwayTrack(length=10, deflection=0, head_station=old_head, tail_station="新站")
        path.tracks.insert(track_row + 1, new_track)

        # 级联更新后续区间起点
        for i in range(track_row, len(path.tracks)):
            if i == 0:
                path.tracks[i].start_point = path.start_point
            else:
                path.tracks[i].start_point = path.tracks[i - 1].end_point()

        self.refresh_rail_track_table(sel_row)
        self.refresh_train_path_table()
        self.rail_track_table.setCurrentCell(track_row + 1, 1)
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        self._refresh_simulation()

    def on_add_track_clicked(self):
        row = self.train_path_table.currentRow()
        if row < 0 or row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[row]
        head = path.tracks[-1].tail_station if path.tracks else "起点"
        track = RailwayTrack(length=10, deflection=0, head_station=head, tail_station="新尾站")
        path.add_track(track)
        new_row = len(path.tracks) - 1
        self.rail_track_table.blockSignals(True)
        self.rail_track_table.insertRow(new_row)
        self._set_track_row(new_row, track)
        self.rail_track_table.blockSignals(False)
        self.refresh_train_path_table()
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        self._refresh_simulation()

    def on_delete_track_clicked(self):
        sel_row = self.train_path_table.currentRow()
        if sel_row < 0 or sel_row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[sel_row]
        if not path.tracks:
            return
        del path.tracks[-1]
        self.rail_track_table.blockSignals(True)
        self.rail_track_table.removeRow(self.rail_track_table.rowCount() - 1)
        self.rail_track_table.blockSignals(False)
        self.refresh_train_path_table()
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        self._refresh_simulation()

    # ── 模拟 ──────────────────────────────────────────

    def _init_simulation(self):
        """初始化模拟：构建索引、加载车次、以当前时间启动"""
        rt_path = config.get_rt_path()
        self._positioner = TrainPositioner(rt_path, self._db, self.train_graph)

        # 取系统当前时间
        now = datetime.now()
        minute = float(now.hour * 60 + now.minute)
        self._sim_clock.current_minute = minute
        self._sim_panel.update_clock(minute)

        # 启动时钟
        self._sim_clock.start()
        self._sim_panel.set_running(True)

    def _refresh_simulation(self):
        """重建模拟索引（保留当前时间，用于 track 属性变更后刷新）"""
        if not self._positioner:
            return
        rt_path = config.get_rt_path()
        self._positioner = TrainPositioner(rt_path, self._db, self.train_graph)
        # 立即用当前时钟时间刷新列车位置
        self._on_sim_tick(self._sim_clock.current_minute)

    def _on_sim_tick(self, minute: float):
        """时钟每帧回调：更新列车位置和面板时钟"""
        if self._positioner:
            positions = self._positioner.visible_trains(minute)
            self.canvas.set_train_positions(positions)
        if self._sim_panel:
            self._sim_panel.update_clock(minute)

    def closeEvent(self, event):
        if hasattr(self, '_db') and self._db:
            self._db.close()
        super().closeEvent(event)

    # ── 辅助方法 ─────────────────────────────────────────

    def _update_track_positions(self, path):
        for i, track in enumerate(path.tracks):
            track.parent_angle = path.angle
            if i == 0:
                track.start_point = path.start_point
            else:
                track.start_point = path.tracks[i - 1].end_point()

    def _update_path_computed_columns(self, path_row):
        if path_row < 0 or path_row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[path_row]
        self.train_path_table.blockSignals(True)
        self.train_path_table.setItem(path_row, 6, QTableWidgetItem(path.get_first_station() or ""))
        self.train_path_table.setItem(path_row, 7, QTableWidgetItem(path.get_last_station() or ""))
        self.train_path_table.setItem(path_row, 8, QTableWidgetItem(str(path.get_length())))
        self.train_path_table.blockSignals(False)

    def _sync_table_rows(self, table, target_count):
        while table.rowCount() > target_count:
            table.removeRow(table.rowCount() - 1)
        while table.rowCount() < target_count:
            table.insertRow(table.rowCount())
