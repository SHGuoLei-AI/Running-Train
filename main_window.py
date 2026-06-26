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
                    load_train_graph_from_db, save_train_graph_to_db)
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
        self.setWindowTitle(f"Running Train — {config.get_graph_name()}")

        # 手动创建主窗口部件
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(2)
        self.canvas_widget = QWidget()
        central_layout.addWidget(self.canvas_widget, stretch=1)

        # 状态栏
        self._status_bar = self.statusBar()
        self._status_label = QLabel("")
        self._status_bar.addWidget(self._status_label)

        # 菜单栏
        self.menu_graph = self.menuBar().addMenu("图(&G)")
        self.menu_routes = self.menuBar().addMenu("经由(&R)")
        self.menu_tools = self.menuBar().addMenu("工具(&T)")
        self.menu_settings = self.menuBar().addMenu("设置(&S)")
        self.menu_help = self.menuBar().addMenu("帮助(&H)")

        # 图菜单
        self._build_graph_menu()

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

        # 默认从 DB 加载
        self._load_from_db()

        # 自动备份（如果开启）
        if self._get_auto_backup():
            self._do_backup()

        self.graph_name_label = QLabel(self.train_graph.name)
        self.graph_name_label.setStyleSheet("font-size: 12px; font-weight: bold; border: none;")

        self.graph_param_layout = QHBoxLayout()
        self.graph_param_layout.setContentsMargins(0, 0, 0, 0)
        self.graph_param_layout.setSpacing(4)
        self.graph_param_layout.addWidget(self.graph_name_label, stretch=1)

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
        self.rail_track_table.setColumnCount(7)
        self.rail_track_table.setHorizontalHeaderLabels(
            ["画", "头站", "画", "尾站", "长度", "偏转", "头→尾"])
        widths = [20, 80, 20, 80, 40, 30, 48]
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
        self.delete_head_button = QPushButton("  删除头部  ")
        self.delete_head_button.clicked.connect(self.on_delete_head_clicked)
        self.extend_head_button = QPushButton("  头部延伸  ")
        self.extend_head_button.clicked.connect(self.on_extend_head_clicked)
        self.insert_track_button = QPushButton("  插入区间  ")
        self.insert_track_button.clicked.connect(self.on_insert_track_clicked)
        self.extend_tail_button = QPushButton("  尾部延伸  ")
        self.extend_tail_button.clicked.connect(self.on_add_track_clicked)
        self.delete_tail_button = QPushButton("  删除尾部  ")
        self.delete_tail_button.clicked.connect(self.on_delete_tail_clicked)
        self.track_btn_layout.addStretch()
        self.track_btn_layout.addWidget(self.delete_head_button)
        self.track_btn_layout.addWidget(self.extend_head_button)
        self.track_btn_layout.addWidget(self.insert_track_button)
        self.track_btn_layout.addWidget(self.extend_tail_button)
        self.track_btn_layout.addWidget(self.delete_tail_button)

        self.data_panel = QWidget()
        data_layout = QVBoxLayout(self.data_panel)
        data_layout.setContentsMargins(2, 2, 2, 2)
        data_layout.setSpacing(2)
        data_layout.addLayout(self.graph_param_layout)
        data_layout.addWidget(self.train_path_table, stretch=1)
        data_layout.addLayout(self.path_btn_layout)
        data_layout.addWidget(self.rail_track_table, stretch=1)
        data_layout.addLayout(self.track_btn_layout)

        self._default_scale = getattr(self.train_graph, 'default_scale', self.train_graph.scale) or self.train_graph.scale
        self.scale_label = QLabel(f" {self.train_graph.scale}× ")
        self.scale_label.setStyleSheet("font-size: 9px; border: none;")
        self.scale_plus_btn = QPushButton(" + ")
        self.scale_plus_btn.clicked.connect(self.on_scale_plus_clicked)
        self.scale_reset_btn = QPushButton(" # ")
        self.scale_reset_btn.setToolTip(f"重置为默认比例尺 {self._default_scale}×")
        self.scale_reset_btn.clicked.connect(self.on_scale_reset_clicked)
        self.scale_minus_btn = QPushButton(" - ")
        self.scale_minus_btn.clicked.connect(self.on_scale_minus_clicked)
        self.toggle_panel_btn = QPushButton(" ▸ ")
        self.toggle_panel_btn.setToolTip("显示/隐藏数据面板")
        self.toggle_panel_btn.clicked.connect(self.on_toggle_panel_clicked)
        scale_btn_row = QHBoxLayout()
        scale_btn_row.setContentsMargins(0, 0, 0, 0)
        scale_btn_row.addStretch()
        scale_btn_row.addWidget(self.scale_label)
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
        # 记录当前图为最近使用
        config.record_recent_graph(config.load_graphs().get('active', ''))

    # ── 菜单 & 信号 ──────────────────────────────────────

    def connect_signals(self):
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
        return config.get_auto_backup()

    def _set_auto_backup(self, enabled):
        config.set_auto_backup(enabled)

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
        """构建图菜单。"""
        self.menu_graph.clear()
        graphs = config.load_graphs().get('graphs', [])
        active_id = config.load_graphs().get('active', '')

        # — 最近 3 个图 —
        recent_ids = config.get_recent_graphs(3)
        id_to_graph = {g['id']: g for g in graphs}
        shown = set()
        for rid in recent_ids:
            g = id_to_graph.get(rid)
            if g and rid not in shown:
                gname = config.get_graph_name(rid)
                action = self.menu_graph.addAction(gname)
                action.setCheckable(True)
                if rid == active_id:
                    action.setChecked(True)
                action.triggered.connect(lambda checked, gid=rid: self._on_switch_graph(gid))
                shown.add(rid)

        # — 更多... —
        other_graphs = [g for g in graphs if g['id'] not in shown]
        if other_graphs:
            self.action_more_graphs = self.menu_graph.addAction("更多...")
            self.action_more_graphs.triggered.connect(self._on_more_graphs)

        self.menu_graph.addSeparator()

        # — 新建 —
        self.action_new_graph = self.menu_graph.addAction("新建")
        self.action_new_graph.triggered.connect(self._on_new_graph)

        # — 属性 —
        self.action_graph_props = self.menu_graph.addAction("属性")
        self.action_graph_props.triggered.connect(self._on_graph_properties)

        # — 导出/导入 JSON —
        self.action_export_json = self.menu_graph.addAction("导出 JSON...")
        self.action_export_json.triggered.connect(self.on_export_json_clicked)
        self.action_import_json = self.menu_graph.addAction("导入 JSON...")
        self.action_import_json.triggered.connect(self.on_import_json_clicked)

        self.menu_graph.addSeparator()

        # — 导入车次 —
        self.action_import_trains = self.menu_graph.addAction("导入车次")
        self.action_import_trains.triggered.connect(self._on_import_trains)

    def _on_switch_graph(self, graph_id: str):
        """切换激活图并重新加载。"""
        if graph_id == config.load_graphs().get('active', ''):
            return
        config.set_active_graph(graph_id)
        config.record_recent_graph(graph_id)
        # 关闭旧连接，打开新连接
        if hasattr(self, '_db') and self._db:
            self._db.close()
        db_path = config.get_rg_path()
        self._db = sqlite3.connect(db_path)
        self.setWindowTitle(f"Running Train — {config.get_graph_name()}")
        # 重新加载
        self._load_from_db()
        self._refresh_graph_ui()
        # 应用默认速度
        default_speed = config.get_default_speed()
        try:
            idx = self._sim_panel.SPEEDS.index(default_speed)
        except ValueError:
            idx = 1
        self._sim_panel.speed_combo.setCurrentIndex(idx)
        self._sim_clock.set_speed(default_speed)
        # 重建模拟
        self._refresh_simulation()
        self._build_graph_menu()

    def _on_more_graphs(self):
        """弹出对话框选择其他图。"""
        graphs = config.load_graphs().get('graphs', [])
        active_id = config.load_graphs().get('active', '')
        recent_ids = config.get_recent_graphs(3)
        # 排除已在菜单中显示的 recent 图
        other = [g for g in graphs if g['id'] not in recent_ids]
        if not other:
            QMessageBox.information(self, "更多图", "没有其他图。")
            return
        names = [config.get_graph_name(g['id']) for g in other]
        name, ok = QInputDialog.getItem(self, "选择图", "图:", names, 0, False)
        if ok and name:
            for g in other:
                if config.get_graph_name(g['id']) == name:
                    self._on_switch_graph(g['id'])
                    break

    def _on_new_graph(self):
        """新建图：输入名称，生成 rg-xxx.db 和 rt-xxx.db。"""
        name, ok = QInputDialog.getText(self, "新建图", "图名称（英文标识）:", text="xinjiang2")
        if not ok or not name.strip():
            return
        gid = name.strip()
        rg_name = f'data/rg-{gid}.db'
        rt_name = f'data/rt-{gid}.db'

        # 检查是否已存在
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        rg_path = os.path.join(data_dir, f'rg-{gid}.db')
        rt_path = os.path.join(data_dir, f'rt-{gid}.db')
        if os.path.exists(rg_path) or os.path.exists(rt_path):
            QMessageBox.warning(self, "新建图", f"图 '{gid}' 的数据库文件已存在。")
            return

        # 创建 rg.db
        import sqlite3
        conn = sqlite3.connect(rg_path)
        conn.executescript('''
            CREATE TABLE train_graph (name TEXT PRIMARY KEY, length INTEGER, width INTEGER,
                scale INTEGER DEFAULT 1, default_scale INTEGER DEFAULT 1,
                default_speed REAL DEFAULT 1.0, rg_version INTEGER DEFAULT 1,
                kl_version TEXT DEFAULT '', cc_version TEXT DEFAULT '',
                author TEXT DEFAULT '');
            CREATE TABLE railway_path (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                kl_line_name TEXT, start_x INTEGER, start_y INTEGER, angle INTEGER DEFAULT 0,
                hidden INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0);
            CREATE TABLE railway_track (id INTEGER PRIMARY KEY AUTOINCREMENT,
                path_id INTEGER REFERENCES railway_path(id), seq INTEGER NOT NULL,
                head_station TEXT, tail_station TEXT, length INTEGER, deflection INTEGER DEFAULT 0,
                draw_head INTEGER DEFAULT 1, draw_tail INTEGER DEFAULT 0,
                label_flip INTEGER DEFAULT 0, is_down INTEGER DEFAULT 1);
            CREATE TABLE routes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                start_station TEXT NOT NULL, end_station TEXT NOT NULL, total_distance INTEGER,
                junction_count INTEGER DEFAULT 0, prohibit_high_speed INTEGER DEFAULT 0,
                prohibit_normal_speed INTEGER DEFAULT 0);
            CREATE TABLE route_stations (id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER REFERENCES routes(id), seq INTEGER NOT NULL,
                station_name TEXT NOT NULL, line_name TEXT NOT NULL, cum_distance INTEGER DEFAULT 0,
                is_junction INTEGER DEFAULT 0);
            INSERT INTO train_graph VALUES (?, 1000, 600, 1, 1, 1.0, 1, '', '', '');
        ''', (gid,))
        conn.commit()
        conn.close()

        # 创建 rt.db
        conn2 = sqlite3.connect(rt_path)
        conn2.executescript('''
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE region_trains (train_name TEXT PRIMARY KEY, from_station TEXT, to_station TEXT);
            CREATE TABLE train_stops (train_name TEXT NOT NULL, stop_seq INTEGER NOT NULL,
                station_name TEXT NOT NULL, arrive_time TEXT, depart_time TEXT,
                distance_km INTEGER DEFAULT 0, segment_train_no TEXT,
                PRIMARY KEY (train_name, stop_seq));
            CREATE TABLE train_route_matches (id INTEGER PRIMARY KEY AUTOINCREMENT,
                train_name TEXT NOT NULL, seg_start_seq INTEGER, seg_end_seq INTEGER,
                seg_start_station TEXT, seg_end_station TEXT, seg_distance_km INTEGER,
                route_id INTEGER, route_name TEXT, is_reverse INTEGER DEFAULT 0,
                match_type TEXT, is_matched INTEGER DEFAULT 1,
                FOREIGN KEY (train_name) REFERENCES region_trains(train_name));
            INSERT INTO meta VALUES ('cc_version','');
            INSERT INTO meta VALUES ('rg_version','1');
        ''')
        conn2.commit()
        conn2.close()

        # 注册到配置
        config.add_graph(gid, rg_name, rt_name)
        config.record_recent_graph(gid)

        # 切换到新图
        self._db.close()
        self._db = sqlite3.connect(rg_path)
        self._load_from_db()
        self._refresh_graph_ui()
        self._refresh_simulation()
        self._build_graph_menu()

    def _on_graph_properties(self):
        """编辑当前图属性。"""
        from PySide6.QtWidgets import QDialog, QFormLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("图属性")
        layout = QFormLayout(dlg)

        name_edit = QLineEdit(self.train_graph.name)
        length_edit = QLineEdit(str(int(self.train_graph.length)))
        width_edit = QLineEdit(str(int(self.train_graph.width)))
        ds_edit = QLineEdit(str(int(getattr(self.train_graph, 'default_scale', 1) or 1)))
        speed_edit = QLineEdit(str(config.get_default_speed()))

        layout.addRow("名称:", name_edit)
        layout.addRow("逻辑长 (km):", length_edit)
        layout.addRow("逻辑宽 (km):", width_edit)
        layout.addRow("默认比例尺:", ds_edit)
        layout.addRow("默认速度:", speed_edit)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addRow(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.train_graph.name = name_edit.text().strip()
            self.train_graph.length = int(float(length_edit.text().strip()))
            self.train_graph.width = int(float(width_edit.text().strip()))
            self.train_graph.default_scale = int(float(ds_edit.text().strip()))
            self._default_scale = self.train_graph.default_scale
            new_speed = float(speed_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, "图属性", "数值格式错误。")
            return

        # 保存到 DB（name/default_speed 存在 train_graph 表中）
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)

        # 刷新
        self._refresh_graph_ui()
        self._build_graph_menu()
        self.setWindowTitle(f"Running Train — {self.train_graph.name}")
        self._sim_clock.set_speed(new_speed)
        try:
            idx = self._sim_panel.SPEEDS.index(new_speed)
            self._sim_panel.speed_combo.setCurrentIndex(idx)
        except ValueError:
            pass

    def _on_import_trains(self):
        """从时刻表（cc.db）导入经过本图车站的所有车次到 rt.db。"""
        # 1. 收集本图所有车站
        graph_stations = set()
        for path in self.train_graph.train_paths:
            for track in path.tracks:
                if track.head_station:
                    graph_stations.add(track.head_station)
                if track.tail_station:
                    graph_stations.add(track.tail_station)
        if not graph_stations:
            QMessageBox.information(self, "导入车次", "当前图中没有任何车站。\n请先在 track 表中添加车站。")
            return

        # 2. 从 cc.db 查出经过这些车站的所有车次
        cc_path = os.path.join(os.path.dirname(__file__), 'data', 'cc.db')
        cc = sqlite3.connect(cc_path)

        placeholders = ','.join('?' * len(graph_stations))
        train_rows = cc.execute(
            f'SELECT DISTINCT t.train_index, t.train_name, t.from_station, t.to_station '
            f'FROM trains t JOIN train_stops ts ON t.train_index = ts.train_index '
            f'WHERE ts.station_name IN ({placeholders}) '
            f'ORDER BY t.train_name',
            list(graph_stations)
        ).fetchall()

        if not train_rows:
            cc.close()
            QMessageBox.information(self, "导入车次", "时刻表中没有找到经过本图车站的车次。")
            return

        # 3. 获取所有车次的完整停站
        train_indices = [r[0] for r in train_rows]

        # 分批查询（避免 SQL 参数过多）
        BATCH = 500
        stop_rows = []
        for b in range(0, len(train_indices), BATCH):
            batch = train_indices[b:b + BATCH]
            ph = ','.join('?' * len(batch))
            rows = cc.execute(
                f'SELECT t.train_name, ts.stop_seq, ts.station_name, '
                f'ts.arrive_time, ts.depart_time, ts.distance_km, ts.segment_train_no '
                f'FROM trains t JOIN train_stops ts ON t.train_index = ts.train_index '
                f'WHERE t.train_index IN ({ph}) '
                f'ORDER BY t.train_index, ts.stop_seq',
                batch
            ).fetchall()
            stop_rows.extend(rows)

        # 获取 cc 版本号
        cc_version = cc.execute('SELECT value FROM meta WHERE key="version"').fetchone()
        cc.close()

        # 4. 写入 rt.db
        rt_path = config.get_rt_path()
        rt = sqlite3.connect(rt_path)
        rt.execute('DELETE FROM train_route_matches')  # 旧的匹配结果失效
        rt.execute('DELETE FROM train_stops')
        rt.execute('DELETE FROM region_trains')

        rt.executemany(
            'INSERT INTO region_trains (train_name, from_station, to_station) VALUES (?,?,?)',
            [(r[1], r[2], r[3]) for r in train_rows]
        )
        rt.executemany(
            'INSERT INTO train_stops (train_name, stop_seq, station_name, arrive_time, depart_time, distance_km, segment_train_no) '
            'VALUES (?,?,?,?,?,?,?)',
            stop_rows
        )

        # 更新版本号
        if cc_version:
            rt.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('cc_version', cc_version[0]))
            # 同步更新 rg.db train_graph
            self._db.execute('UPDATE train_graph SET cc_version=?', (cc_version[0],))
            self._db.commit()
        rt.commit()
        rt.close()

        # 5. 刷新匹配
        self._refresh_simulation()

        QMessageBox.information(
            self, "导入车次",
            f"导入完成！\n\n"
            f"图内车站：{len(graph_stations)} 个\n"
            f"导入车次：{len(train_rows)} 趟\n"
            f"总停站记录：{len(stop_rows)} 条\n\n"
            f"旧的匹配结果已清空，请运行「经由 → 车次匹配」重新匹配。"
        )

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
            self._on_scale_changed()

    def on_scale_reset_clicked(self):
        self.train_graph.scale = self._default_scale
        self._on_scale_changed()

    def on_scale_minus_clicked(self):
        if self.train_graph.scale > 1:
            self.train_graph.scale -= 1
            self._on_scale_changed()

    def _on_scale_changed(self):
        self.scale_label.setText(f" {self.train_graph.scale}× ")
        self.canvas._update_size()
        self.update_graph_param_fields()
        self.canvas.update()
        self._refresh_simulation()

    # ── DB I/O ──────────────────────────────────────────

    def _load_from_db(self, graph_name=None):
        self.train_graph = load_train_graph_from_db(self._db)
        self._current_graph_name = self.train_graph.name
        self._default_scale = getattr(self.train_graph, 'default_scale', self.train_graph.scale) or self.train_graph.scale
        self.canvas = DrawingCanvas(self.train_graph)
        self.canvas.mouse_status.connect(self._on_canvas_mouse_status)
        if hasattr(self, 'scroll_area'):
            self.scroll_area.setWidget(self.canvas)

    def _refresh_graph_ui(self):
        """刷新右侧面板：path 表、track 表、图属性字段、画布。"""
        if hasattr(self, 'train_path_table'):
            self.refresh_train_path_table()
        if hasattr(self, 'rail_track_table'):
            self.rail_track_table.setRowCount(0)
        if hasattr(self, 'graph_name_label'):
            self.update_graph_param_fields()
        if hasattr(self, 'canvas'):
            self.canvas._update_size()
            self.canvas.update()

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
        if hasattr(self, 'graph_name_label'):
            self.graph_name_label.setText(self.train_graph.name)
        if hasattr(self, 'scale_label'):
            self.scale_label.setText(f" {self.train_graph.scale}× ")

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

        # 选择方向
        from PySide6.QtWidgets import QInputDialog
        direction_choice = QInputDialog.getItem(
            self, "选择方向", f"请指定 [{line_name}] 从 {first_station} 到 {last_station} 的方向：",
            ["下行（头→尾）", "上行（头→尾）"], 0, False)
        if not direction_choice:
            return
        is_down = 0 if direction_choice.startswith('上行') else 1

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
                draw_head=is_first, draw_tail=is_last,
                is_down=is_down))

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
        # 头→尾 方向（点击切换 下行/上行）
        is_down_val = getattr(track, 'is_down', 1)
        if is_down_val is None:
            is_down_val = 1
        is_down_item = QTableWidgetItem('下行' if is_down_val else '上行')
        is_down_item.setFlags(is_down_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.rail_track_table.setItem(row, 6, is_down_item)

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

    def on_track_table_cell_clicked(self, row, col):
        if col in (0, 2):
            # 画头站/画尾站 checkbox
            item = self.rail_track_table.item(row, col)
            if not item:
                return
            current = item.data(Qt.ItemDataRole.CheckStateRole)
            new_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setData(Qt.ItemDataRole.CheckStateRole, new_state)
        elif col == 6:
            # 头→尾 方向：点击切换 下行/上行
            item = self.rail_track_table.item(row, col)
            if not item:
                return
            current = item.text()
            new_val = '上行' if current == '下行' else '下行'
            item.setText(new_val)
            sel_row = self.train_path_table.currentRow()
            if 0 <= sel_row < len(self.train_graph.train_paths):
                path = self.train_graph.train_paths[sel_row]
                if row < len(path.tracks):
                    track = path.tracks[row]
                    track.is_down = 1 if new_val == '下行' else 0
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
        inherit_is_down = getattr(path.tracks[0], 'is_down', 1)
        if inherit_is_down is None:
            inherit_is_down = 1
        new_track = RailwayTrack(length=10, deflection=0, head_station="新头站", tail_station=old_head,
                                 is_down=inherit_is_down)
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

        inherit_is_down = getattr(path.tracks[track_row], 'is_down', 1)
        if inherit_is_down is None:
            inherit_is_down = 1
        new_track = RailwayTrack(length=10, deflection=0, head_station=old_head, tail_station="新站",
                                 is_down=inherit_is_down)
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
        inherit_is_down = getattr(path.tracks[-1], 'is_down', 1) if path.tracks else 1
        if inherit_is_down is None:
            inherit_is_down = 1
        track = RailwayTrack(length=10, deflection=0, head_station=head, tail_station="新尾站",
                             is_down=inherit_is_down)
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

    def on_delete_head_clicked(self):
        """删除当前选中 path 的第一个 track（头部）。"""
        sel_row = self.train_path_table.currentRow()
        if sel_row < 0 or sel_row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[sel_row]
        if not path.tracks:
            return
        # 删除第一个 track，path 起点移到下一个 track 的 head
        removed = path.tracks.pop(0)
        if path.tracks:
            path.start_point = path.tracks[0].start_point
        else:
            path.start_point = removed.end_point()  # 空 path 时起点移到原尾部
        self.refresh_rail_track_table(sel_row)
        self.refresh_train_path_table()
        self.canvas.update()
        from models import save_train_graph_to_db
        save_train_graph_to_db(self.train_graph, self._db)
        self._refresh_simulation()

    def on_delete_tail_clicked(self):
        """删除当前选中 path 的最后一个 track（尾部）。"""
        sel_row = self.train_path_table.currentRow()
        if sel_row < 0 or sel_row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[sel_row]
        if not path.tracks:
            return
        del path.tracks[-1]
        self.refresh_rail_track_table(sel_row)
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

        # 缓存车次→起讫站映射（用于状态栏悬停提示）
        self._train_info: dict[str, tuple[str, str]] = {}
        try:
            rt_conn = sqlite3.connect(rt_path)
            rows = rt_conn.execute(
                'SELECT train_name, from_station, to_station FROM region_trains'
            ).fetchall()
            self._train_info = {r[0]: (r[1], r[2]) for r in rows}
            rt_conn.close()
        except Exception:
            pass

        # 设置默认速度
        default_speed = config.get_default_speed()
        try:
            idx = self._sim_panel.SPEEDS.index(default_speed)
        except ValueError:
            idx = 1  # fallback to 1×
        self._sim_panel.speed_combo.setCurrentIndex(idx)
        self._sim_clock.set_speed(default_speed)

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

    # ── 状态栏 ──────────────────────────────────────────

    def _on_canvas_mouse_status(self, text: str):
        # 解析列车悬停信息（格式： ...  |||train_name|||）
        if '|||' in text:
            parts = text.split('|||')
            base = parts[0]
            train_name = parts[1] if len(parts) > 1 else ''
            info = self._train_info.get(train_name, (None, None))
            if info[0] and info[1]:
                base += f'  [{train_name}，{info[0]} -- {info[1]}]'
            else:
                base += f'  [{train_name}]'
            self._status_label.setText(base)
        else:
            self._status_label.setText(text)

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
