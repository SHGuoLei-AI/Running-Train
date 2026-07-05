"""车站状态面板 — 左侧，时钟控制面板下方

下拉框选择车站（按经停列车数排序），下方绘制当前时刻站内列车：
- 始发列车（提前5分钟出现）
- 终到列车（延迟5分钟消失）
- 停站中的列车
按距发车/消失时刻排序，最近的排最上面。

列车形状（定宽矩形 + 两侧端形，端形宽 CAP_W）：
  下行停站中 > C701 >   左内凹(>切入) + 右外凸(>凸出)
  上行停站中 < C702 <   左外凸(<凸出) + 右内凹(<切入)
  下行始发   || G1001 >  左平直        + 右外凸(>凸出)
  上行始发   < G1002 ||  左外凸(<凸出) + 右平直
  下行终到   > D2113 ||  左内凹(>切入) + 右平直
  上行终到   || D2114 <  左平直        + 右内凹(<切入)

  外凸三角：端形在框外，尖在远端（x-lcap 或 x+rcap）
  内凹三角：端形切入框内，尖在框内（x+lcap 或 x-rcap）
"""
import sqlite3
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QComboBox,
                                QScrollArea, QFrame, QLabel)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (QPainter, QPen, QBrush, QColor, QFont,
                            QPainterPath, QPolygonF)


CAP_W = 8          # 两端端形宽度（三角形/矩形）
ROW_H = 20         # 每行高度（上下各留白2px）
BOX_MIN_W = 60     # 中心矩形最小宽度（容纳最长5位车次号）
FONT_SIZE = 10     # 车次号字号
LIST_MIN_W = 96    # 列表最小宽度


def train_color(train_name: str) -> QColor:
    """根据车次首字母返回颜色。"""
    prefix = train_name[0] if train_name else 'K'
    if prefix == 'G':
        return QColor(220, 50, 50)
    elif prefix in ('D', 'C'):
        return QColor(255, 140, 0)
    else:
        return QColor(50, 150, 50)


def _parse_minute(t: str | None) -> int | None:
    """'HH:MM' → 分钟数 (0-1439)，空/None → None"""
    if not t:
        return None
    parts = t.split(':')
    if len(parts) >= 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            return None
    return None


class _TrainRow:
    """站内一趟列车的信息"""
    __slots__ = ('train_name', 'display_name', 'stop_type', 'is_down',
                 'dep_time', 'prefix')
    def __init__(self, train_name: str, display_name: str, stop_type: str,
                 is_down: bool, dep_time: int, prefix: str):
        self.train_name = train_name
        self.display_name = display_name
        self.stop_type = stop_type
        self.is_down = is_down
        self.dep_time = dep_time
        self.prefix = prefix


class _TrainListWidget(QWidget):
    """绘制站内列车列表的自定义 widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[_TrainRow] = []
        self.setMinimumWidth(LIST_MIN_W)

    def set_rows(self, rows: list[_TrainRow]):
        self._rows = rows
        self.setFixedHeight(max(len(rows) * ROW_H + 4, 20))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._rows:
            return

        font = QFont()
        font.setPixelSize(FONT_SIZE)
        font.setBold(True)
        painter.setFont(font)

        panel_w = self.width()

        for idx, row in enumerate(self._rows):
            y_top = idx * ROW_H + 2       # 上留白2px
            h = ROW_H - 4                 # 形状实际高度（上下各留白2px）
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(row.display_name)
            box_w = max(text_w + 8, BOX_MIN_W)

            # 居中
            total_w = 2 * CAP_W + box_w
            x = max(0, (panel_w - total_w) / 2)

            self._draw_shape(painter, x, y_top, box_w, h, row)

            # 文字（白色加粗，居中在矩形内）
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            text_x = x + CAP_W + (box_w - text_w) / 2
            text_y = y_top + (h + fm.ascent() - fm.descent()) / 2
            painter.drawText(QPointF(text_x, text_y), row.display_name)

    def _draw_shape(self, painter: QPainter, x: float, y: float,
                    box_w: float, h: float, row: _TrainRow):
        """绘制列车形状多边形。

        坐标系（x 从左到右）：
          l0 = box_l - CAP_W   左外凸尖 / 左平直边
          l1 = box_l           框左边界
          l2 = box_l + CAP_W   左内凹尖
          l0 = box_l - CAP_W   左外凸尖/左平直边/左内凹外口
          r2 = box_r + CAP_W   右外凸尖/右平直边/右内凹外口

        外凸三角：端形在框外，尖在 l0 或 r2，底在框边(box_l/box_r)
        内凹三角：外口在 l0 或 r2，尖在框边中点(box_l/box_r,YM)
        平直：端形为矩形填满 [l0,box_l] 或 [box_r,r2]
        """
        YT, YM, YB = y, y + h / 2, y + h

        box_l = x + CAP_W
        box_r = box_l + box_w
        l0 = box_l - CAP_W
        r2 = box_r + CAP_W

        # 确定左右端类型
        if row.stop_type == 'departure':
            lt, rt = ('flat', 'out') if row.is_down else ('out', 'flat')
        elif row.stop_type == 'arrival':
            lt, rt = ('in', 'flat') if row.is_down else ('flat', 'in')
        else:  # stop
            lt, rt = ('in', 'out') if row.is_down else ('out', 'in')

        # 6 种组合的顺时针顶点序列
        VERTEX_MAP = {
            # 下行停站中: left inward(>外口l0尖box_l) + right outward(>尖r2)
            ('in', 'out'):  [(l0,YT), (box_l,YM), (l0,YB),
                             (box_r,YB), (r2,YM), (box_r,YT), (box_l,YT)],
            # 上行停站中: left outward(<尖l0) + right inward(<外口r2尖box_r)
            ('out', 'in'):  [(l0,YM), (box_l,YT),
                             (box_r,YT), (r2,YT), (box_r,YM), (r2,YB),
                             (box_r,YB), (box_l,YB)],
            # 下行始发: left flat + right outward(>尖r2)
            ('flat', 'out'): [(l0,YT), (box_l,YT),
                              (box_r,YT), (r2,YM),
                              (box_r,YB), (box_l,YB), (l0,YB)],
            # 上行始发: left outward(<尖l0) + right flat
            ('out', 'flat'): [(l0,YM), (box_l,YT),
                              (box_r,YT), (r2,YT),
                              (r2,YB), (box_r,YB), (box_l,YB)],
            # 下行终到: left inward(>外口l0尖box_l) + right flat
            ('in', 'flat'):  [(l0,YT), (box_l,YM), (l0,YB),
                              (box_r,YB), (r2,YB), (r2,YT),
                              (box_r,YT), (box_l,YT)],
            # 上行终到: left flat + right inward(<外口r2尖box_r)
            ('flat', 'in'):  [(l0,YT), (box_l,YT),
                              (box_r,YT), (r2,YT), (box_r,YM), (r2,YB),
                              (box_r,YB), (box_l,YB), (l0,YB)],
        }

        pts = VERTEX_MAP[(lt, rt)]

        color = train_color(row.train_name)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.GlobalColor.black, 1))

        poly = QPolygonF([QPointF(px, py) for px, py in pts])
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        painter.drawPath(path)


class StationStatusWidget(QWidget):
    """车站状态面板：下拉框 + 站内列车列表"""

    def __init__(self, rt_db_path: str, rg_conn, train_graph, parent=None):
        super().__init__(parent)
        self.setFixedWidth(100)
        self._rt_db_path = rt_db_path
        self._rg_conn = rg_conn
        self._train_graph = train_graph

        self._station_data: dict[str, list[tuple]] = {}
        self._all_train_stops: dict[str, list[tuple]] = {}
        self._current_station: str | None = None
        self._current_minute: float = 0.0

        self._setup_ui()
        self.reload_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        # 标题
        title = QLabel("车站状态")
        title.setStyleSheet(
            "font-size: 12px; font-weight: bold; padding: 2px 0;"
            "border: none; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 下拉框
        self._combo = QComboBox()
        self._combo.setFixedHeight(24)
        self._combo.setStyleSheet(
            "QComboBox { font-size: 10px; padding: 1px 4px; }"
            "QComboBox QAbstractItemView { font-size: 10px; }"
            "QComboBox::drop-down { width: 14px; }")
        self._combo.currentTextChanged.connect(self._on_station_changed)
        layout.addWidget(self._combo)

        # 滚动区域 + 列车列表
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }")

        self._train_list = _TrainListWidget()
        self._scroll.setWidget(self._train_list)
        layout.addWidget(self._scroll, stretch=1)

    # ── 数据加载 ────────────────────────────────────────────

    def reload_data(self):
        """从 rt.db 加载车站和车次数据。"""
        self._station_data.clear()
        self._all_train_stops.clear()

        try:
            rt = sqlite3.connect(self._rt_db_path)
        except Exception:
            return

        graph_stations: set[str] = set()
        for path in self._train_graph.train_paths:
            for track in path.tracks:
                if track.head_station:
                    graph_stations.add(track.head_station)
                if track.tail_station:
                    graph_stations.add(track.tail_station)

        if not graph_stations:
            rt.close()
            return

        placeholders = ','.join('?' * len(graph_stations))
        rows = rt.execute(
            'SELECT train_name, stop_seq, station_name, arrive_time, '
            'depart_time, distance_km, segment_train_no '
            'FROM train_stops '
            f'WHERE station_name IN ({placeholders}) '
            'ORDER BY train_name, stop_seq',
            list(graph_stations)
        ).fetchall()

        for r in rows:
            tn = r[0]
            self._all_train_stops.setdefault(tn, []).append(r)

        for r in rows:
            stn = r[2]
            self._station_data.setdefault(stn, []).append(r)

        # 加载匹配方向：train_name → {stop_seq: is_reverse}
        self._stop_reverse: dict[str, dict[int, bool]] = {}
        try:
            mr = rt.execute(
                "SELECT train_name, seg_start_seq, seg_end_seq, is_reverse "
                "FROM train_route_matches WHERE match_type='matched'"
            ).fetchall()
            for train_name, s0, s1, rev in mr:
                d = self._stop_reverse.setdefault(train_name, {})
                for seq in range(s0, s1 + 1):
                    d[seq] = bool(rev)
        except Exception:
            pass
        rt.close()

        counts = [(stn, len(set(r[0] for r in trains)))
                  for stn, trains in self._station_data.items()]
        counts.sort(key=lambda x: (-x[1], x[0]))

        self._combo.blockSignals(True)
        self._combo.clear()
        for stn, cnt in counts:
            self._combo.addItem(f"{stn} ({cnt})", stn)
        if self._combo.count() > 0:
            self._combo.setCurrentIndex(0)
            self._current_station = self._combo.itemData(0)
        self._combo.blockSignals(False)

        self._refresh_trains()

    # ── 时间更新 ────────────────────────────────────────────

    def update_time(self, minute: float):
        self._current_minute = minute
        self._refresh_trains()

    # ── 内部 ────────────────────────────────────────────────

    def _on_station_changed(self, text: str):
        idx = self._combo.currentIndex()
        if idx >= 0:
            self._current_station = self._combo.itemData(idx)
        self._refresh_trains()

    def _refresh_trains(self):
        if not self._current_station:
            self._train_list.set_rows([])
            return

        stn = self._current_station
        minute = self._current_minute
        rows: list[_TrainRow] = []

        for r in self._station_data.get(stn, []):
            train_name, stop_seq, _stn, arrive, depart, dist_km, seg_no = r
            arr = _parse_minute(arrive)
            dep = _parse_minute(depart)
            if arr is None or dep is None:
                continue  # 数据不完整，跳过

            # 始发/终到/经停 由首末站判定（arr/dep 时刻表均非空）
            all_stops = self._all_train_stops.get(train_name, [])
            first_seq = all_stops[0][1] if all_stops else stop_seq
            last_seq = all_stops[-1][1] if all_stops else stop_seq

            if stop_seq == first_seq and stop_seq == last_seq:
                continue  # 只有一站，跳过

            found = False
            stop_type = ''
            event_time = 0
            for day_off in (-1, 0, 1):
                a = arr + 1440 * day_off
                d = dep + 1440 * day_off

                if stop_seq == first_seq:
                    # 始发：提前5分钟出现，发车后消失
                    if d - 5 <= minute <= d:
                        stop_type = 'departure'; event_time = d
                        found = True; break
                elif stop_seq == last_seq:
                    # 终到：到站后出现，延后5分钟消失
                    if a <= minute <= a + 5:
                        stop_type = 'arrival'; event_time = a + 5
                        found = True; break
                else:
                    # 经停：到站→发车
                    if a <= minute <= d:
                        stop_type = 'stop'; event_time = d
                        found = True; break

            if not found:
                continue

            is_down = self._get_direction(train_name, stop_seq)
            display = seg_no or train_name
            prefix = train_name[0] if train_name else 'K'

            rows.append(_TrainRow(
                train_name=train_name, display_name=display,
                stop_type=stop_type, is_down=is_down,
                dep_time=event_time, prefix=prefix))

        rows.sort(key=lambda r: r.dep_time - minute)
        self._train_list.set_rows(rows)

    def _get_direction(self, train_name: str, stop_seq: int) -> bool:
        """判断列车在该站是否为下行：查 train_route_matches.is_reverse。"""
        rev_map = self._stop_reverse.get(train_name, {})
        if stop_seq in rev_map:
            return not rev_map[stop_seq]  # is_reverse=1 → 上行(not down)
        return True  # 默认下行
