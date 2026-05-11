import os
from PySide6.QtWidgets import (QMainWindow, QMessageBox, QWidget, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLineEdit, QFileDialog, QScrollArea)
from PySide6.QtCore import Qt
from models import (TrainGraph, RailwayPath, RailwayTrack,
                    load_train_graph_from_json, save_train_graph_to_json)
from canvas import DrawingCanvas
from delegates import RadioDelegate


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Running Train Application")
        self._refreshing = False
        self._current_file_path = None

        # 手动创建主窗口部件
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        self.canvas_widget = QWidget()
        central_layout.addWidget(self.canvas_widget)

        # 菜单栏
        self.menu_file = self.menuBar().addMenu("文件(&F)")
        self.menu_help = self.menuBar().addMenu("帮助(&H)")
        self.action_exit = self.menu_file.addAction("退出")
        self.action_about = self.menu_help.addAction("关于")

        # 文件菜单：打开、保存、另存为
        self.action_open = self.menu_file.addAction("打开(&O)")
        self.action_open.triggered.connect(self.on_open_clicked)
        self.action_save = self.menu_file.addAction("保存(&S)")
        self.action_save.triggered.connect(self.on_save_clicked)
        self.action_save_as = self.menu_file.addAction("另存为(&A)...")
        self.action_save_as.triggered.connect(self.on_save_as_clicked)
        self.menu_file.insertSeparator(self.action_exit)

        # 默认打开 data/上海周边.json
        default_path = os.path.join(os.path.dirname(__file__), 'data', '上海周边.json')
        self._load_from_file(default_path)

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
        self.add_track_button = QPushButton("  新增区间  ")
        self.add_track_button.clicked.connect(self.on_add_track_clicked)
        self.delete_track_button = QPushButton("  删除区间  ")
        self.delete_track_button.clicked.connect(self.on_delete_track_clicked)
        self.track_btn_layout.addStretch()
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
        scale_btn_row = QHBoxLayout()
        scale_btn_row.addStretch()
        scale_btn_row.addWidget(self.scale_plus_btn)
        scale_btn_row.addWidget(self.scale_reset_btn)
        scale_btn_row.addWidget(self.scale_minus_btn)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setWidget(self.canvas)

        left_panel = QVBoxLayout()
        left_panel.addWidget(self.scroll_area, stretch=1)
        left_panel.addLayout(scale_btn_row)

        canvas_layout = self.canvas_widget.layout() or QHBoxLayout(self.canvas_widget)
        while canvas_layout.count():
            canvas_layout.takeAt(0)
        canvas_layout.addLayout(left_panel, stretch=3)
        canvas_layout.addWidget(self.data_panel, stretch=1)

        self.refresh_train_path_table()
        self.update_graph_param_fields()
        self.connect_signals()

    # ── 菜单 & 信号 ──────────────────────────────────────

    def connect_signals(self):
        self.action_exit.triggered.connect(self.close)
        self.action_about.triggered.connect(self.on_about_clicked)

    def on_about_clicked(self):
        QMessageBox.about(self, "关于", "欢迎使用动态模拟火车运行图")

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

    # ── 文件 I/O ─────────────────────────────────────────

    def _load_from_file(self, file_path):
        self._current_file_path = file_path
        self.train_graph = load_train_graph_from_json(file_path)
        self._original_scale = self.train_graph.scale
        self.canvas = DrawingCanvas(self.train_graph)
        if hasattr(self, 'scroll_area'):
            self.scroll_area.setWidget(self.canvas)

    def on_open_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开运行图文件",
            os.path.join(os.path.dirname(__file__), 'data'),
            "JSON 文件 (*.json);;所有文件 (*)")
        if file_path:
            self._load_from_file(file_path)
            self.refresh_train_path_table()
            self.update_graph_param_fields()
            self.path_selected_label.setText("")
            self.rail_track_table.setRowCount(0)
            self.canvas.update()

    def on_save_clicked(self):
        if self._current_file_path:
            save_train_graph_to_json(self.train_graph, self._current_file_path)
        else:
            self.on_save_as_clicked()

    def on_save_as_clicked(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存运行图文件",
            os.path.join(os.path.dirname(__file__), 'data'),
            "JSON 文件 (*.json);;所有文件 (*)")
        if file_path:
            save_train_graph_to_json(self.train_graph, file_path)
            self._current_file_path = file_path

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
                for i in range(row + 1, len(path.tracks)):
                    path.tracks[i].start_point = path.tracks[i - 1].end_point()
            elif col == 5:
                track.deflection = int(float(item.text().strip()))
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
