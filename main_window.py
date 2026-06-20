import json
import os
import sqlite3
from PySide6.QtWidgets import (QMainWindow, QMessageBox, QWidget, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLineEdit, QFileDialog, QScrollArea, QSplitter,
                               QInputDialog)
from PySide6.QtCore import Qt
from models import (TrainGraph, RailwayPath, RailwayTrack,
                    load_train_graph_from_json, save_train_graph_to_json,
                    load_train_graph_from_db, save_train_graph_to_db,
                    list_graphs_in_db)
from canvas import DrawingCanvas
from delegates import RadioDelegate


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Running Train Application")
        self._refreshing = False
        self._current_graph_name = None

        # DB connection (persistent, shared across app lifetime)
        db_path = os.path.join(os.path.dirname(__file__), 'data', 'rg.db')
        self._db = sqlite3.connect(db_path)

        # 手动创建主窗口部件
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        self.canvas_widget = QWidget()
        central_layout.addWidget(self.canvas_widget)

        # 菜单栏
        self.menu_file = self.menuBar().addMenu("文件(&F)")
        self.menu_routes = self.menuBar().addMenu("经由(&R)")
        self.menu_tools = self.menuBar().addMenu("工具(&T)")
        self.menu_help = self.menuBar().addMenu("帮助(&H)")
        self.action_exit = self.menu_file.addAction("退出")
        self.action_route_editor = self.menu_routes.addAction("经由维护...")
        self.menu_routes.addSeparator()
        self.action_route_match = self.menu_routes.addAction("车次匹配...")
        self.menu_routes.addSeparator()
        self.action_route_matched_trains = self.menu_routes.addAction("经由匹配的车次")
        self.action_train_matched_routes = self.menu_routes.addAction("车次匹配的经由")
        self.action_update_schedule = self.menu_tools.addAction("更新时刻表...")
        self.action_update_kl = self.menu_tools.addAction("更新里程表...")
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

        # 默认从 DB 加载
        self._load_from_db()

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
            ["ID", "隐", "线路", "X", "Y", "角度", "首站", "末站", "长度"])
        widths = [40, 20, 150, 40, 40, 40, 80, 80, 40]
        for i, w in enumerate(widths):
            self.train_path_table.setColumnWidth(i, w)
        self.train_path_table.verticalHeader().setFixedWidth(24)
        self.train_path_table.itemSelectionChanged.connect(self.on_train_path_selected)
        self.train_path_table.itemChanged.connect(self.on_path_item_changed)
        self.train_path_table.cellClicked.connect(self.on_path_table_cell_clicked)

        self.path_selected_label = QLabel("")
        self.path_selected_label.setStyleSheet("font-weight: bold; border: none;")

        self.path_btn_layout = QHBoxLayout()
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
        self.path_btn_layout.addWidget(self.add_path_button)
        self.path_btn_layout.addWidget(self.delete_path_button)

        self.rail_track_table = QTableWidget()
        self.rail_track_table.setColumnCount(6)
        self.rail_track_table.setHorizontalHeaderLabels(
            ["画", "头站", "画", "尾站", "长度", "偏转"])
        widths = [20, 80, 20, 80, 40, 30]
        for i, w in enumerate(widths):
            self.rail_track_table.setColumnWidth(i, w)
        self.rail_track_table.verticalHeader().setFixedWidth(24)
        self.rail_track_table.itemChanged.connect(self.on_track_item_changed)
        self.rail_track_table.cellClicked.connect(self.on_track_table_cell_clicked)

        self._radio_delegate = RadioDelegate()
        self.train_path_table.setItemDelegateForColumn(1, self._radio_delegate)
        self.rail_track_table.setItemDelegateForColumn(0, self._radio_delegate)
        self.rail_track_table.setItemDelegateForColumn(2, self._radio_delegate)

        self.track_btn_layout = QHBoxLayout()
        self.insert_track_button = QPushButton("  插入区间  ")
        self.insert_track_button.clicked.connect(self.on_insert_track_clicked)
        self.add_track_button = QPushButton("  新增区间  ")
        self.add_track_button.clicked.connect(self.on_add_track_clicked)
        self.delete_track_button = QPushButton("  删除区间  ")
        self.delete_track_button.clicked.connect(self.on_delete_track_clicked)
        self.track_btn_layout.addStretch()
        self.track_btn_layout.addWidget(self.insert_track_button)
        self.track_btn_layout.addWidget(self.add_track_button)
        self.track_btn_layout.addWidget(self.delete_track_button)

        self.data_panel = QWidget()
        data_layout = QVBoxLayout(self.data_panel)
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
        scale_btn_row.addStretch()
        scale_btn_row.addWidget(self.scale_plus_btn)
        scale_btn_row.addWidget(self.scale_reset_btn)
        scale_btn_row.addWidget(self.scale_minus_btn)
        scale_btn_row.addWidget(self.toggle_panel_btn)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setWidget(self.canvas)

        left_panel = QVBoxLayout()
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
        while canvas_layout.count():
            canvas_layout.takeAt(0)
        canvas_layout.addWidget(self._splitter)

        self.refresh_train_path_table()
        self.update_graph_param_fields()
        self.connect_signals()

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

    def on_update_schedule_clicked(self):
        QMessageBox.information(self, "更新时刻表",
            "从路路通 APK 提取时刻表数据写入 cc.db。\n\n"
            "雏形脚本: tools/parse_llt_apk.py\n"
            "待完善：集成到 GUI，显示进度，自动备份旧版本。")

    def on_update_kl_clicked(self):
        QMessageBox.information(self, "更新里程表",
            "从 jprailfan.com/tools/stat/ 获取最新客里表数据写入 kl.db。\n\n"
            "待完善：实现下载解析逻辑。")

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
        rt_path = os.path.join(os.path.dirname(__file__), 'data', 'rt.db')
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

    def on_scale_reset_clicked(self):
        self.train_graph.scale = self._original_scale
        self.canvas._update_size()
        self.update_graph_param_fields()
        self.canvas.update()

    def on_scale_minus_clicked(self):
        if self.train_graph.scale > 1:
            self.train_graph.scale -= 1
            self.canvas._update_size()
            self.update_graph_param_fields()
            self.canvas.update()

    # ── DB I/O ──────────────────────────────────────────

    def _load_from_db(self, graph_name=None):
        self.train_graph = load_train_graph_from_db(self._db, graph_name)
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

    # ── 线路表 ────────────────────────────────────────────

    def refresh_train_path_table(self):
        self.train_path_table.blockSignals(True)
        n = len(self.train_graph.train_paths)
        self._sync_table_rows(self.train_path_table, n)
        for i, path in enumerate(self.train_graph.train_paths):
            self._set_path_row(i, path)
        self.train_path_table.blockSignals(False)

    def _set_path_row(self, row, path):
        self.train_path_table.setItem(row, 0, QTableWidgetItem(str(path.id)))
        self.train_path_table.setItem(row, 2, QTableWidgetItem(path.name))
        self.train_path_table.setItem(row, 3, QTableWidgetItem(str(int(path.start_point[0]))))
        self.train_path_table.setItem(row, 4, QTableWidgetItem(str(int(path.start_point[1]))))
        self.train_path_table.setItem(row, 5, QTableWidgetItem(str(int(path.angle))))
        self.train_path_table.setItem(row, 6, QTableWidgetItem(path.get_first_station() or ""))
        self.train_path_table.setItem(row, 7, QTableWidgetItem(path.get_last_station() or ""))
        self.train_path_table.setItem(row, 8, QTableWidgetItem(str(path.get_length())))
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsEnabled)
        chk.setData(Qt.ItemDataRole.CheckStateRole,
                    Qt.CheckState.Checked if path.hidden else Qt.CheckState.Unchecked)
        self.train_path_table.setItem(row, 1, chk)

    def on_path_item_changed(self, item):
        if self._refreshing:
            return
        row = item.row()
        col = item.column()
        if row >= len(self.train_graph.train_paths):
            return
        path = self.train_graph.train_paths[row]
        try:
            if col == 0:
                path.id = item.text().strip()
            elif col == 1:
                path.hidden = (item.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked)
            elif col == 2:
                path.name = item.text().strip()
            elif col == 3:
                x = int(float(item.text().strip()))
                path.start_point = (x, path.start_point[1])
                self._update_track_positions(path)
            elif col == 4:
                y = int(float(item.text().strip()))
                path.start_point = (path.start_point[0], y)
                self._update_track_positions(path)
            elif col == 5:
                path.angle = int(float(item.text().strip()))
                self._update_track_positions(path)
        except ValueError:
            pass
        self.canvas._update_size()
        self.canvas.update()

    def on_path_table_cell_clicked(self, row, col):
        if col != 1:
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
        self.train_path_table.setCurrentCell(new_row, 2)
        self.train_path_table.scrollToItem(self.train_path_table.item(new_row, 2))
        self.train_path_table.editItem(self.train_path_table.item(new_row, 2))
        self.canvas.update()

    def on_delete_path_clicked(self):
        row = self.train_path_table.currentRow()
        if row < 0 or row >= len(self.train_graph.train_paths):
            return
        del self.train_graph.train_paths[row]
        self.refresh_train_path_table()
        self.path_selected_label.setText("")
        self.rail_track_table.setRowCount(0)
        self.canvas.update()

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
        self.train_path_table.setCurrentCell(row - 1, 2)
        self.canvas.update()

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
        self.train_path_table.setCurrentCell(row + 1, 2)
        self.canvas.update()

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
        try:
            if col == 0:
                track.draw_head = (item.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked)
            elif col == 1:
                track.head_station = item.text().strip()
            elif col == 2:
                track.draw_tail = (item.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked)
            elif col == 3:
                track.tail_station = item.text().strip()
            elif col == 4:
                track.length = int(float(item.text().strip()))
            elif col == 5:
                track.deflection = int(float(item.text().strip()))

            if col in (4, 5):
                for i in range(row + 1, len(path.tracks)):
                    path.tracks[i].start_point = path.tracks[i - 1].end_point()
        except ValueError:
            pass
        self._update_path_computed_columns(sel_row)
        self.canvas._update_size()
        self.canvas.update()

    def on_track_table_cell_clicked(self, row, col):
        if col not in (0, 2):
            return
        item = self.rail_track_table.item(row, col)
        if not item:
            return
        current = item.data(Qt.ItemDataRole.CheckStateRole)
        new_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
        item.setData(Qt.ItemDataRole.CheckStateRole, new_state)

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
