import math
import sys
import json
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QWidget, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,
                               QDialog, QDialogButtonBox, QFormLayout, QPushButton, QLineEdit)
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QPen, QColor
from ui.main_window import Ui_MainWindow

TRACK_WIDTH = 2

class TrainGraph:
    """列车运行图类"""
    def __init__(self, name, length=1000, width=600, scale=1, **kwargs):
        self.name = name
        self.length = length
        self.width = width
        self.scale = scale
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.train_paths = []      # 列车路径列表
        self.train_points = []    # 火车点列表

    def add_train_path(self, path):
        """添加列车路径"""
        self.train_paths.append(path)

    def add_train_point(self, point):
        """添加火车点"""
        self.train_points.append(point)

    def get_all_tracks(self):
        """获取所有轨道"""
        tracks = []
        for path in self.train_paths:
            tracks.extend(path.tracks)
        return tracks

class RailwayPath:
    """铁路线路类"""
    def __init__(self, path_id, name, start_x, start_y, angle=0.0, hidden=False, **kwargs):
        self.id = path_id
        self.name = name
        self.start_point = (start_x, start_y)
        self.angle = angle
        self.hidden = hidden
        self.tracks = []
        for key, value in kwargs.items():
            setattr(self, key, value)

    def add_track(self, track):
        if self.tracks:
            track.start_point = self.tracks[-1].end_point()
        else:
            track.start_point = self.start_point
        track.parent_angle = self.angle
        self.tracks.append(track)
        return track

    def get_first_station(self):
        return self.tracks[0].head_station if self.tracks else None

    def get_last_station(self):
        return self.tracks[-1].tail_station if self.tracks else None

    def get_length(self):
        return sum(track.length for track in self.tracks)

class RailwayTrack:
    """铁路区间类"""
    def __init__(self, length, deflection, head_station="", tail_station="", draw_head=True, draw_tail=False, start_point=(0, 0), **kwargs):
        self.length = length              # 区间长度（公里）
        self.deflection = deflection      # 绘制偏转角度（度）
        self.head_station = head_station  # 头站
        self.tail_station = tail_station  # 尾站
        self.draw_head = draw_head        # 头站名称绘制
        self.draw_tail = draw_tail        # 尾站名称绘制
        self.start_point = start_point    # 起始点 (x, y)
        self.parent_angle = 0.0           # 所属线路基准角度
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def actual_angle(self):
        return self.parent_angle + self.deflection

    def end_point(self):
        radians = math.radians(self.actual_angle)
        return (
            self.start_point[0] + self.length * math.cos(radians),
            self.start_point[1] + self.length * math.sin(radians),
        )

class TrainPoint:
    """火车点类"""
    def __init__(self, direction, start_position, speed_ratio, stop_time, color=None, track=None):
        self.direction = direction
        self.start_position = start_position
        self.speed_ratio = speed_ratio
        self.stop_time = stop_time
        self.color = color
        self.track = track
        self.current_position = start_position
        self.visible = True
        self.moving = True
        self.hide_timer = None

class DrawingCanvas(QWidget):
    """自定义绘制画布"""
    def __init__(self, train_graph, parent=None):
        super().__init__(parent)
        self.train_graph = train_graph

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(128, 128, 128))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QColor(255, 250, 205))

        for track in self.train_graph.get_all_tracks():
            painter.save()
            painter.translate(track.start_point[0], track.start_point[1])
            painter.rotate(track.actual_angle)
            painter.drawRect(0, -TRACK_WIDTH/2, track.length, TRACK_WIDTH)
            painter.restore()

        for point in self.train_graph.train_points:
            if not point.visible or not point.track: continue
            color = QColor(255, 0, 0) if point.direction == "down" else QColor(0, 0, 255)
            if point.color == "green": color = QColor(0, 255, 0)
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            circle_radius = 1.5
            track = point.track
            local_x = track.length * point.current_position
            point_coords = QPointF(local_x, 0)
            transform = painter.transform()
            transform.translate(track.start_point[0], track.start_point[1])
            transform.rotate(track.actual_angle)
            transformed_point = transform.map(point_coords)
            painter.drawEllipse(transformed_point, circle_radius, circle_radius)

    def move_train_points(self, base_step_ratio):
        for point in self.train_graph.train_points:
            if not point.moving or not point.visible: continue
            step = base_step_ratio * point.speed_ratio
            if point.direction == "down":
                point.current_position = min(point.current_position + step, 1.0)
                if point.current_position >= 1.0: point.moving = False
            else:
                point.current_position = max(point.current_position - step, 0.0)
                if point.current_position <= 0.0: point.moving = False
        self.update()

    def reset_train_points(self):
        for point in self.train_graph.train_points:
            point.current_position = point.start_position
            point.visible, point.moving = True, True
            if point.hide_timer: point.hide_timer.stop()
        self.update()

    def hide_train_point(self, train_point):
        train_point.visible = False
        self.update()

class EditGraphDialog(QDialog):
    def __init__(self, train_graph, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑运行图参数")
        form_layout = QFormLayout(self)
        self.name_edit = QLineEdit(train_graph.name)
        self.length_edit = QLineEdit(str(train_graph.length))
        self.width_edit = QLineEdit(str(train_graph.width))
        self.scale_edit = QLineEdit(str(train_graph.scale))
        form_layout.addRow("名称:", self.name_edit)
        form_layout.addRow("长:", self.length_edit)
        form_layout.addRow("宽:", self.width_edit)
        form_layout.addRow("比例尺:", self.scale_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        form_layout.addWidget(button_box)

    def get_values(self):
        return (self.name_edit.text().strip(), self.length_edit.text().strip(), 
                self.width_edit.text().strip(), self.scale_edit.text().strip())

class MainWindow(QMainWindow):
    @staticmethod
    def load_train_graph_from_json(json_file_path):
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        g = data['TrainGraph']
        train_graph = TrainGraph(name=g['name'], length=g['length'], width=g['width'], scale=g.get('scale', 1))
        for p_data in g['paths']:
            path = RailwayPath(path_id=p_data['id'], name=p_data['name'], start_x=p_data['start_x'], 
                               start_y=p_data['start_y'], angle=p_data.get('angle', 0.0), hidden=p_data.get('hidden', False))
            for t_data in p_data['tracks']:
                path.add_track(RailwayTrack(length=t_data['length'], deflection=t_data['deflection'], 
                                            head_station=t_data.get('head_station', ""), tail_station=t_data.get('tail_station', ""), 
                                            draw_head=t_data.get('draw_start', True), draw_tail=t_data.get('draw_end', False)))
            train_graph.add_train_path(path)
        return train_graph

    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        json_file_path = os.path.join(os.path.dirname(__file__), 'data', '上海周边.json')
        self.train_graph = self.load_train_graph_from_json(json_file_path)
        self.canvas = DrawingCanvas(self.train_graph)
        
        self.graph_title_label = QLabel(self.train_graph.name)
        self.graph_title_label.setStyleSheet("font-size: 12px; font-weight: bold; border: none;")

        self.graph_length_field = QLineEdit(str(self.train_graph.length))
        self.graph_width_field = QLineEdit(str(self.train_graph.width))
        self.graph_scale_field = QLineEdit(str(self.train_graph.scale))

        self.edit_graph_button = QPushButton("编辑")
        self.edit_graph_button.setFixedWidth(100)
        self.edit_graph_button.clicked.connect(self.on_edit_graph_clicked)

        self.graph_param_layout = QHBoxLayout()
        self.graph_param_layout.addWidget(QLabel("长:")); self.graph_param_layout.addWidget(self.graph_length_field)
        self.graph_param_layout.addWidget(QLabel("宽:")); self.graph_param_layout.addWidget(self.graph_width_field)
        self.graph_param_layout.addWidget(QLabel("比例尺:")); self.graph_param_layout.addWidget(self.graph_scale_field)
        self.graph_param_layout.addWidget(self.edit_graph_button)

        self.train_path_table = QTableWidget()
        self.train_path_table.setColumnCount(8)
        self.train_path_table.setHorizontalHeaderLabels(["ID", "画", "线路", "X", "Y", "首站", "末站", "长度"])
        widths = [40, 20, 150, 40, 40, 80, 80, 40]
        for i, w in enumerate(widths): self.train_path_table.setColumnWidth(i, w)
        self.train_path_table.setMaximumHeight(250)
        self.train_path_table.itemSelectionChanged.connect(self.on_train_path_selected)

        self.path_selected_label = QLabel("")
        self.path_selected_label.setStyleSheet("font-weight: bold; border: none;")

        self.rail_track_table = QTableWidget()
        self.rail_track_table.setColumnCount(6)
        self.rail_track_table.setHorizontalHeaderLabels(["头站", "画", "尾站", "画", "长度", "偏转"])
        widths = [80, 20, 80, 20, 40, 30]
        for i, w in enumerate(widths): self.rail_track_table.setColumnWidth(i, w)
        
        self.data_panel = QWidget()
        data_layout = QVBoxLayout(self.data_panel)
        data_layout.addWidget(self.graph_title_label)
        data_layout.addLayout(self.graph_param_layout)
        data_layout.addWidget(self.train_path_table)
        data_layout.addWidget(self.path_selected_label)
        data_layout.addWidget(self.rail_track_table)
        
        canvas_layout = self.ui.canvas_widget.layout() or QHBoxLayout(self.ui.canvas_widget)
        while canvas_layout.count(): canvas_layout.takeAt(0)
        canvas_layout.addWidget(self.canvas, stretch=3)
        canvas_layout.addWidget(self.data_panel, stretch=1)

        self.clock_label = QLabel("Day 0 00:00")
        self.clock_label.setFixedWidth(120)
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ui.button_layout.insertWidget(0, self.clock_label)

        self.current_day, self.current_minutes = 0, 0
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.advance_clock)
        self.clock_timer.start(1000)

        # 示例数据
        if self.train_graph.train_paths:
            p1 = self.train_graph.train_paths[0]
            if p1.tracks:
                self.train_graph.add_train_point(TrainPoint("down", 0.15, 1.0, 12000, track=p1.tracks[0]))
                self.train_graph.add_train_point(TrainPoint("up", 0.55, 0.7, 15000, track=p1.tracks[0]))
            if len(self.train_graph.train_paths) > 1:
                p2 = self.train_graph.train_paths[1]
                if p2.tracks:
                    self.train_graph.add_train_point(TrainPoint("down", 0.30, 0.5, 5000, "green", track=p2.tracks[0]))

        self.refresh_train_path_table()
        self.update_graph_param_fields()
        self.speed_ratio = 12
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_train_points_position)
        self.connect_signals()

    def connect_signals(self):
        self.ui.start_button.clicked.connect(self.on_start_clicked)
        self.ui.stop_button.clicked.connect(self.on_stop_clicked)
        self.ui.reset_button.clicked.connect(self.on_reset_clicked)
        self.ui.action_exit.triggered.connect(self.close)
        self.ui.action_about.triggered.connect(self.on_about_clicked)

    def on_start_clicked(self):
        self.animation_timer.stop()
        for p in self.train_graph.train_points:
            if p.hide_timer: p.hide_timer.stop()
        self.canvas.reset_train_points()
        self.animation_timer.start(50)

    def on_stop_clicked(self):
        self.animation_timer.stop()

    def on_reset_clicked(self):
        self.animation_timer.stop()
        for p in self.train_graph.train_points:
            if p.hide_timer: p.hide_timer.stop()
        self.canvas.reset_train_points()

    def update_train_points_position(self):
        step_ratio = 0.032 * self.speed_ratio * (50 / 1000.0)
        self.canvas.move_train_points(step_ratio)
        for point in self.train_graph.train_points:
            if not point.moving and point.visible and not point.hide_timer:
                point.hide_timer = QTimer(self)
                point.hide_timer.setSingleShot(True)
                point.hide_timer.timeout.connect(lambda p=point: self.canvas.hide_train_point(p))
                point.hide_timer.start(point.stop_time)
        if all(not point.moving for point in self.train_graph.train_points):
            self.animation_timer.stop()

    def advance_clock(self):
        self.current_minutes += 1
        if self.current_minutes >= 1440:
            self.current_minutes = 0
            self.current_day = (self.current_day + 1) % 366
        self.clock_label.setText(f"Day {self.current_day} {self.current_minutes//60:02d}:{self.current_minutes%60:02d}")

    def on_about_clicked(self):
        QMessageBox.about(self, "关于", "欢迎使用动态模拟火车运行图")

    def update_graph_param_fields(self):
        self.graph_title_label.setText(self.train_graph.name)
        self.graph_length_field.setText(str(self.train_graph.length))
        self.graph_width_field.setText(str(self.train_graph.width))
        self.graph_scale_field.setText(str(self.train_graph.scale))

    def on_edit_graph_clicked(self):
        dialog = EditGraphDialog(self.train_graph, self)
        if dialog.exec() == QDialog.Accepted:
            v = dialog.get_values()
            try:
                self.train_graph.name, self.train_graph.length = v[0], float(v[1])
                self.train_graph.width, self.train_graph.scale = float(v[2]), float(v[3])
                self.update_graph_param_fields()
            except ValueError:
                QMessageBox.warning(self, "输入错误", "请输入数值。")

    def refresh_train_path_table(self):
        self.train_path_table.setRowCount(0)
        for i, path in enumerate(self.train_graph.train_paths):
            self.train_path_table.insertRow(i)
            self.train_path_table.setItem(i, 0, QTableWidgetItem(str(path.id)))
            self.train_path_table.setItem(i, 2, QTableWidgetItem(path.name))
            self.train_path_table.setItem(i, 3, QTableWidgetItem(str(path.start_point[0])))
            self.train_path_table.setItem(i, 4, QTableWidgetItem(str(path.start_point[1])))
            self.train_path_table.setItem(i, 5, QTableWidgetItem(path.get_first_station() or ""))
            self.train_path_table.setItem(i, 6, QTableWidgetItem(path.get_last_station() or ""))
            self.train_path_table.setItem(i, 7, QTableWidgetItem(str(path.get_length())))
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked if path.hidden else Qt.CheckState.Unchecked)
            self.train_path_table.setItem(i, 1, chk)

    def on_train_path_selected(self):
        row = self.train_path_table.currentRow()
        if 0 <= row < len(self.train_graph.train_paths):
            path = self.train_graph.train_paths[row]
            self.path_selected_label.setText(path.name)
            self.refresh_rail_track_table(row)

    def refresh_rail_track_table(self, idx):
        self.rail_track_table.setRowCount(0)
        path = self.train_graph.train_paths[idx]
        for i, t in enumerate(path.tracks):
            self.rail_track_table.insertRow(i)
            self.rail_track_table.setItem(i, 0, QTableWidgetItem(t.head_station))
            self.rail_track_table.setItem(i, 2, QTableWidgetItem(t.tail_station))
            self.rail_track_table.setItem(i, 4, QTableWidgetItem(str(t.length)))
            self.rail_track_table.setItem(i, 5, QTableWidgetItem(str(t.deflection)))
            chkh = QTableWidgetItem()
            chkh.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chkh.setCheckState(Qt.CheckState.Checked if t.draw_head else Qt.CheckState.Unchecked)
            self.rail_track_table.setItem(i, 1, chkh)
            chkt = QTableWidgetItem()
            chkt.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chkt.setCheckState(Qt.CheckState.Checked if t.draw_tail else Qt.CheckState.Unchecked)
            self.rail_track_table.setItem(i, 3, chkt)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())