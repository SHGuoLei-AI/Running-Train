import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QPainter, QPen, QColor

from simulation import TrainRenderer

TRACK_WIDTH = 10
UP_LINE_COLOR = QColor(255, 200, 200)
DOWN_LINE_COLOR = QColor(200, 255, 200)


class DrawingCanvas(QWidget):
    """自定义绘制画布"""

    NEARBY_THRESHOLD = 15  # 像素，判定"靠近"端点/列车的距离

    mouse_status = Signal(str)  # 格式化状态文本（末尾可含 |||train_name|||）

    def __init__(self, train_graph, parent=None):
        super().__init__(parent)
        self.train_graph = train_graph
        self._train_positions: list = []  # list of TrainPosition
        self.setMouseTracking(True)
        self._update_size()

    def set_train_positions(self, positions: list):
        """设置要绘制的列车位置列表，触发重绘"""
        self._train_positions = positions
        self.update()

    def mouseMoveEvent(self, event):
        """跟踪鼠标位置，查找附近线路、车站、列车，发射状态文本"""
        scale = self.train_graph.scale
        px = event.position().x()
        py = event.position().y()
        km_x = px / scale if scale else 0
        km_y = py / scale if scale else 0

        lines = self._find_nearby_lines(px, py)
        stations = self._find_nearby_stations(px, py)
        trains = self._find_nearby_trains(px, py)

        # 格式：坐标；线路；车站；车次
        status = f"X：{km_x:.0f} km，Y：{km_y:.0f} km"
        if lines:
            status += f"；线路：{'、'.join(lines)}"
        if stations:
            status += f"；车站：{'、'.join(stations)}"
        if trains:
            for t in trains:
                status += f"|||{t}|||"

        self.mouse_status.emit(status)
        super().mouseMoveEvent(event)

    @staticmethod
    def _point_to_segment_distance(px: float, py: float,
                                    x1: float, y1: float,
                                    x2: float, y2: float) -> float:
        """点到线段的最短距离。"""
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    def _find_nearby_lines(self, px: float, py: float) -> list[str]:
        """查找鼠标附近所有线路名（track 线段到鼠标距离 < NEARBY_THRESHOLD）。"""
        scale = self.train_graph.scale
        nearby: list[str] = []
        seen: set[str] = set()

        for path in self.train_graph.train_paths:
            if path.hidden:
                continue
            for track in path.tracks:
                sx, sy = track.start_point
                x1 = sx * scale
                y1 = sy * scale
                ex, ey = track.end_point()
                x2 = ex * scale
                y2 = ey * scale

                dist = self._point_to_segment_distance(px, py, x1, y1, x2, y2)
                if dist < self.NEARBY_THRESHOLD and path.name not in seen:
                    nearby.append(path.name)
                    seen.add(path.name)
                    break  # 每个 path 只需一个 track 命中
        return nearby

    def _find_nearby_stations(self, px: float, py: float) -> list[str]:
        """查找鼠标附近所有站名（track 端点距离 < NEARBY_THRESHOLD）。"""
        scale = self.train_graph.scale
        nearby: list[str] = []
        seen: set[str] = set()

        for track in self.train_graph.get_all_tracks():
            sx, sy = track.start_point
            hx = sx * scale
            hy = sy * scale
            ex, ey = track.end_point()
            tx = ex * scale
            ty = ey * scale

            dh = math.hypot(px - hx, py - hy)
            if dh < self.NEARBY_THRESHOLD and track.head_station not in seen:
                nearby.append(track.head_station)
                seen.add(track.head_station)

            dt = math.hypot(px - tx, py - ty)
            if dt < self.NEARBY_THRESHOLD and track.tail_station not in seen:
                nearby.append(track.tail_station)
                seen.add(track.tail_station)

        return nearby

    def _find_nearby_trains(self, px: float, py: float) -> list[str]:
        """查找鼠标附近所有列车名（列车圆距离 < NEARBY_THRESHOLD）。"""
        nearby: list[str] = []
        seen: set[str] = set()
        for pos in self._train_positions:
            d = math.hypot(px - pos.x, py - pos.y)
            if d < self.NEARBY_THRESHOLD:
                name = (pos.train_name or pos.label).strip()
                if name and name not in seen:
                    nearby.append(name)
                    seen.add(name)
        return nearby

    def _update_size(self):
        scale = self.train_graph.scale
        max_x = max_y = 0
        for track in self.train_graph.get_all_tracks():
            x1 = track.start_point[0] * scale
            y1 = track.start_point[1] * scale
            ex, ey = track.end_point()
            x2 = ex * scale
            y2 = ey * scale
            max_x = max(max_x, x1, x2)
            max_y = max(max_y, y1, y2)
        margin = 60
        self.setMinimumSize(int(max_x + margin), int(max_y + margin))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = self.train_graph.scale
        tracks = self.train_graph.get_all_tracks()

        # 第1遍：画所有线段（中线、上/下行线、车站标记线）
        for track in tracks:
            painter.save()
            x = track.start_point[0] * scale
            y = track.start_point[1] * scale
            length = track.length * scale
            painter.translate(x, y)
            painter.rotate(track.actual_angle)

            painter.setPen(QPen(Qt.GlobalColor.black, 1))
            painter.drawLine(0, 0, int(length), 0)

            painter.setPen(QPen(UP_LINE_COLOR, 1))
            painter.drawLine(0, TRACK_WIDTH, int(length), TRACK_WIDTH)

            painter.setPen(QPen(DOWN_LINE_COLOR, 1))
            painter.drawLine(0, -TRACK_WIDTH, int(length), -TRACK_WIDTH)

            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawLine(0, -TRACK_WIDTH, 0, TRACK_WIDTH)
            painter.drawLine(int(length), -TRACK_WIDTH, int(length), TRACK_WIDTH)

            painter.restore()

        # 第2遍：画站名（白底黑字，压住下面的线）
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.black, 1))

        for track in tracks:
            length = track.length * scale
            x = track.start_point[0] * scale
            y = track.start_point[1] * scale
            radians = math.radians(track.actual_angle)

            if track.draw_head:
                painter.save()
                painter.translate(x, y)
                pw = painter.fontMetrics().horizontalAdvance(track.head_station)
                fh = painter.fontMetrics().height()
                text_rect = QRect(-pw // 2 - 2, -fh // 2, pw + 4, fh)
                painter.fillRect(text_rect, QColor(255, 255, 255))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, track.head_station)
                painter.restore()

            if track.draw_tail:
                painter.save()
                ex = int(x + length * math.cos(radians))
                ey = int(y + length * math.sin(radians))
                painter.translate(ex, ey)
                pw = painter.fontMetrics().horizontalAdvance(track.tail_station)
                fh = painter.fontMetrics().height()
                text_rect = QRect(-pw // 2 - 2, -fh // 2, pw + 4, fh)
                painter.fillRect(text_rect, QColor(255, 255, 255))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, track.tail_station)
                painter.restore()

        # 第3遍：画列车（圆点 + 车次号，覆盖在线路上方）
        for pos in self._train_positions:
            TrainRenderer.draw(painter, pos)
