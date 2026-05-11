import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPen, QColor

TRACK_WIDTH = 10
UP_LINE_COLOR = QColor(255, 200, 200)
DOWN_LINE_COLOR = QColor(200, 255, 200)


class DrawingCanvas(QWidget):
    """自定义绘制画布"""
    def __init__(self, train_graph, parent=None):
        super().__init__(parent)
        self.train_graph = train_graph
        self._update_size()

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
