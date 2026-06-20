"""列车运行模拟核心模块

SegmentIndex: 站对→画布坐标映射
TrainPositioner: 车次→时刻→画布位置
SimulationClock: 模拟时钟 0-1439 分钟循环
TrainRenderer: 列车绘制
"""
import math
import re
import time
import sqlite3
from collections import deque
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer, Qt, QPointF
from PySide6.QtGui import QColor, QPen, QBrush


# ——————————————————————————————————————
# 颜色工具（模块级，TrainPositioner 和 TrainRenderer 共用）
# ——————————————————————————————————————

def train_color(train_name: str) -> QColor:
    """根据车次首字母返回颜色：G=红, D/C=橙, 其他=绿"""
    prefix = train_name[0] if train_name else 'K'
    if prefix == 'G':
        return QColor(220, 50, 50)
    elif prefix in ('D', 'C'):
        return QColor(255, 140, 0)
    else:
        return QColor(50, 150, 50)


# ——————————————————————————————————————
# 数据结构
# ——————————————————————————————————————

@dataclass
class TrackInfo:
    """画布坐标系下的区段信息"""
    head_station: str
    tail_station: str
    x1: int
    y1: int
    x2: int
    y2: int
    length_km: int
    angle_rad: float
    path_code: str = ""
    label_flip: int = 0


@dataclass
class TrainStop:
    """一趟车次的一个停站"""
    station_name: str
    arr_min: Optional[int]    # 到达分钟数，None=无到达（始发站只有出发）
    dep_min: Optional[int]    # 出发分钟数，None=无出发（终到站只有到达）
    dist_km: int
    segment_train_no: Optional[str] = None  # 复车次当前单号


@dataclass
class TrainPosition:
    """列车在画布上的位置"""
    x: float
    y: float
    label: str      # 显示用的车次号
    color: QColor
    label_flip: int = 0  # 0=正画, 1=反画（本段 track 的 label_flip）


# ——————————————————————————————————————
# SegmentIndex
# ——————————————————————————————————————

class SegmentIndex:
    """站对→画布区段映射，从 TrainGraph 构建"""

    def __init__(self):
        self.segment_map: dict[tuple, TrackInfo] = {}   # (stn_a, stn_b) → TrackInfo
        self.station_map: dict[str, list[TrackInfo]] = {}  # 站名 → 所在区段列表

    @classmethod
    def from_graph(cls, train_graph) -> "SegmentIndex":
        idx = cls()
        scale = train_graph.scale
        for path in train_graph.train_paths:
            if path.hidden:
                continue
            path_code = getattr(path, 'id', '') or ''
            for track in path.tracks:
                sx, sy = track.start_point
                ex, ey = track.end_point()
                info = TrackInfo(
                    head_station=track.head_station,
                    tail_station=track.tail_station,
                    x1=int(sx * scale), y1=int(sy * scale),
                    x2=int(ex * scale), y2=int(ey * scale),
                    length_km=track.length,
                    angle_rad=math.radians(track.actual_angle),
                    path_code=str(path_code),
                    label_flip=getattr(track, 'label_flip', 0),
                )
                # 双向索引（同一 TrackInfo 对象，通过 head/tail 判断方向）
                idx.segment_map[(track.head_station, track.tail_station)] = info
                idx.segment_map[(track.tail_station, track.head_station)] = info
                for stn in (track.head_station, track.tail_station):
                    if stn:
                        idx.station_map.setdefault(stn, []).append(info)
        return idx

    def lookup(self, stn_a: str, stn_b: str) -> Optional[TrackInfo]:
        """查两站之间的区段，返回 TrackInfo（含方向信息）"""
        return self.segment_map.get((stn_a, stn_b))

    def find_path(self, stn_a: str, stn_b: str) -> Optional[list[TrackInfo]]:
        """BFS 找两站之间的 track 序列（用于跨多个区段的列车停站）"""
        # 直连快速路径
        direct = self.segment_map.get((stn_a, stn_b))
        if direct is not None:
            return [direct]

        if stn_a not in self.station_map or stn_b not in self.station_map:
            return None

        visited = {stn_a}
        queue: deque[tuple[str, list[TrackInfo]]] = deque()
        queue.append((stn_a, []))

        while queue:
            stn, path = queue.popleft()
            for track in self.station_map.get(stn, []):
                other = track.tail_station if stn == track.head_station else track.head_station
                if other in visited:
                    continue
                new_path = path + [track]
                if other == stn_b:
                    return new_path
                visited.add(other)
                queue.append((other, new_path))

        return None

    def __len__(self):
        return len(self.segment_map)


# ——————————————————————————————————————
# TrainPositioner
# ——————————————————————————————————————

TRACK_OFFSET = 10  # 上行/下行距中心线的像素偏移量


def _parse_minute(t: Optional[str]) -> Optional[int]:
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


def _get_line_sign(train_label: str) -> int:
    """根据车次号最末数字段奇偶判断上/下行：奇数=上行(+1)，偶数=下行(-1)"""
    nums = re.findall(r'\d+', train_label)
    if nums:
        return 1 if int(nums[-1]) % 2 == 1 else -1
    return 1  # 默认上行


def _perpendicular_offset(angle_rad: float, sign: int) -> tuple[float, float]:
    """垂直轨道方向的偏移量：上行 +10px，下行 -10px"""
    # 轨道局部坐标系中 y+10 对应全局的 (-sin, cos) 方向
    return sign * TRACK_OFFSET * -math.sin(angle_rad), sign * TRACK_OFFSET * math.cos(angle_rad)


class TrainPositioner:
    """根据模拟时钟计算所有车次的画布位置"""

    def __init__(self, rt_db_path: str, segment_index: SegmentIndex):
        self._seg = segment_index
        self._trains: dict[str, list[TrainStop]] = {}        # train_name → 有序停站
        self._seg_paths: dict[tuple[str, int], list[TrackInfo]] = {}  # (train_name, i) → tracks
        self._load(rt_db_path)
        self._build_paths()

    def _load(self, db_path: str):
        """从 rt.db 加载所有车次的停站序列"""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                'SELECT train_name, stop_seq, station_name, arrive_time, depart_time, '
                'distance_km, segment_train_no '
                'FROM train_stops ORDER BY train_name, stop_seq'
            ).fetchall()

            current_train = None
            stops: list[TrainStop] = []
            for r in rows:
                tn = r['train_name']
                if tn != current_train:
                    if stops:
                        self._trains[current_train] = stops
                    current_train = tn
                    stops = []

                arr = _parse_minute(r['arrive_time'])
                dep = _parse_minute(r['depart_time'])
                stops.append(TrainStop(
                    station_name=r['station_name'],
                    arr_min=arr,
                    dep_min=dep,
                    dist_km=r['distance_km'],
                    segment_train_no=r['segment_train_no'],
                ))

            if stops and current_train:
                self._trains[current_train] = stops
        finally:
            conn.close()

    def _build_paths(self):
        """预计算每个车次每对连续停站之间的 track 序列（含多跳 BFS）"""
        for train_name, stops in self._trains.items():
            for i in range(len(stops) - 1):
                a = stops[i].station_name
                b = stops[i + 1].station_name
                path = self._seg.find_path(a, b)
                if path:
                    self._seg_paths[(train_name, i)] = path

    def position(self, train_name: str, minute: float) -> Optional[TrainPosition]:
        """计算一趟车在指定时刻的画布位置

        使用归一化时间线（以 first_dep 为基准，跨天时间 +1440）避免午夜判断。
        """
        stops = self._trains.get(train_name)
        if not stops or len(stops) < 2:
            return None

        first_dep = stops[0].dep_min
        last_arr = stops[-1].arr_min
        if first_dep is None or last_arr is None:
            return None

        # — 归一化所有停站时间 —
        # 以 first_dep 为基准，小于 first_dep 的 += 1440（跨午夜）
        norm: list[tuple[Optional[int], Optional[int]]] = []
        for s in stops:
            a = s.arr_min
            d = s.dep_min
            if a is not None and a < first_dep:
                a += 1440
            if d is not None and d < first_dep:
                d += 1440
            norm.append((a, d))

        T = minute
        if T < first_dep:
            T += 1440
        if T > norm[-1][0]:  # T > 末站到达
            return None
        if T < first_dep:
            return None

        # — 查找 T 所在区间 —
        for i in range(len(stops)):
            arr_i, dep_i = norm[i]

            # 停站中？arr[i] ≤ T ≤ dep[i]
            if arr_i is not None and dep_i is not None and arr_i <= T <= dep_i:
                return self._at_station(stops, i, train_name)

            # 区间运行？dep[i] < T < arr[i+1]
            if i < len(stops) - 1:
                arr_next = norm[i + 1][0]
                if dep_i is not None and arr_next is not None and dep_i < T < arr_next:
                    return self._running(stops, i, train_name, T, dep_i, arr_next)

        return None

    def _at_station(self, stops: list[TrainStop], i: int, train_name: str) -> Optional[TrainPosition]:
        """列车停在 stops[i]，取相邻 track 的本站端坐标，偏移到上/下行线"""
        label = stops[i].segment_train_no or train_name
        color = train_color(train_name)
        sign = _get_line_sign(label)

        # 终到站：取上一段的最后一条 track 的终点
        if i >= len(stops) - 1:
            if i > 0:
                tracks = self._seg_paths.get((train_name, i - 1))
                if tracks:
                    last_track = tracks[-1]
                    is_forward = (stops[i].station_name == last_track.tail_station)
                    if is_forward:
                        x, y = last_track.x2, last_track.y2
                    else:
                        x, y = last_track.x1, last_track.y1
                    dx, dy = _perpendicular_offset(last_track.angle_rad, sign)
                    return TrainPosition(x=x + dx, y=y + dy, label=label, color=color,
                                         label_flip=last_track.label_flip)
            return None

        # 一般停站：取下一段的第一条 track 的本站端
        tracks = self._seg_paths.get((train_name, i))
        if not tracks:
            return None

        first_track = tracks[0]
        is_head = (stops[i].station_name == first_track.head_station)
        if is_head:
            x, y = first_track.x1, first_track.y1
        else:
            x, y = first_track.x2, first_track.y2
        dx, dy = _perpendicular_offset(first_track.angle_rad, sign)

        return TrainPosition(x=x + dx, y=y + dy, label=label, color=color,
                             label_flip=first_track.label_flip)

    def _running(self, stops: list[TrainStop], i: int, train_name: str,
                 T: float, dep: int, arr: int) -> Optional[TrainPosition]:
        """列车在 stops[i]→stops[i+1] 区间运行（可能跨多个 track），偏移到上/下行线"""
        seg_dist = stops[i + 1].dist_km - stops[i].dist_km
        if seg_dist <= 0:
            return self._at_station(stops, i, train_name)

        tracks = self._seg_paths.get((train_name, i))
        if not tracks:
            return None

        label = stops[i].segment_train_no or train_name
        sign = _get_line_sign(label)

        time_ratio = (T - dep) / (arr - dep)
        traveled = time_ratio * seg_dist

        # 沿 track 序列逐段定位，追踪进入每段的方向
        entry_stn = stops[i].station_name
        acc = 0.0
        for ti, track in enumerate(tracks):
            tk_len = track.length_km
            is_last = (ti == len(tracks) - 1)
            is_forward = (entry_stn == track.head_station)
            exit_stn = track.tail_station if is_forward else track.head_station

            if traveled <= acc + tk_len or is_last:
                local = traveled - acc
                ratio = local / tk_len if tk_len > 0 else 0.0
                if not is_forward:
                    ratio = 1.0 - ratio
                ratio = max(0.0, min(1.0, ratio))

                x = track.x1 + ratio * (track.x2 - track.x1)
                y = track.y1 + ratio * (track.y2 - track.y1)
                dx, dy = _perpendicular_offset(track.angle_rad, sign)

                return TrainPosition(x=x + dx, y=y + dy, label=label,
                                     color=train_color(train_name),
                                     label_flip=track.label_flip)

            acc += tk_len
            entry_stn = exit_stn

        # fallback
        last_track = tracks[-1]
        dx, dy = _perpendicular_offset(last_track.angle_rad, sign)
        return TrainPosition(x=last_track.x2 + dx, y=last_track.y2 + dy,
                             label=label, color=train_color(train_name),
                             label_flip=last_track.label_flip)

    def visible_trains(self, minute: float) -> list[TrainPosition]:
        """获取指定时刻所有可见列车位置"""
        result = []
        for train_name in self._trains:
            pos = self.position(train_name, minute)
            if pos is not None:
                result.append(pos)
        return result

    @property
    def train_count(self) -> int:
        return len(self._trains)


# ——————————————————————————————————————
# SimulationClock
# ——————————————————————————————————————

class SimulationClock(QObject):
    """24小时循环模拟时钟，QTimer 驱动"""

    time_changed = Signal(float)  # current_minute (0.0 ~ 1440.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_minute = 0.0
        self.speed = 1.0           # sim minutes per real second
        self._paused = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(33)  # ~30 fps
        self._last_tick: Optional[float] = None

    @property
    def paused(self) -> bool:
        return self._paused

    def _tick(self):
        if self._paused:
            return
        now = time.perf_counter()
        if self._last_tick is not None:
            dt = now - self._last_tick
            self.current_minute += dt * self.speed
            while self.current_minute >= 1440.0:
                self.current_minute -= 1440.0
            while self.current_minute < 0.0:
                self.current_minute += 1440.0
            self.time_changed.emit(self.current_minute)
        self._last_tick = now

    def start(self):
        """开始/恢复运行"""
        self._paused = False
        self._last_tick = time.perf_counter()
        self._timer.start()

    def pause(self):
        """暂停"""
        self._paused = True
        self._timer.stop()
        self._last_tick = None

    def stop(self):
        """停止并重置到 0:00"""
        self.pause()
        self.current_minute = 0.0
        self.time_changed.emit(0.0)

    def jump_to(self, hour: int):
        """跳转到整点 (0-23)"""
        self.current_minute = float(hour * 60)
        self.time_changed.emit(self.current_minute)

    def set_speed(self, speed: float):
        self.speed = speed


# ——————————————————————————————————————
# TrainRenderer
# ——————————————————————————————————————

class TrainRenderer:
    """列车静态绘制方法"""

    @staticmethod
    def draw(painter, pos: TrainPosition):
        """画一个列车：5px 实心圆 + 车次号（上行右上，下行左下）"""
        painter.save()

        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(pos.color)
        painter.drawEllipse(QPointF(pos.x, pos.y), 5, 5)

        font = painter.font()
        font.setPixelSize(8)
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        sign = _get_line_sign(pos.label)
        # label_flip 反画时上下行标签位置互换
        flip = pos.label_flip
        if (sign == 1 and flip == 0) or (sign == -1 and flip == 1):
            # 上行正画 / 下行反画 → 车次号在左下
            tw = painter.fontMetrics().horizontalAdvance(pos.label)
            fh = painter.fontMetrics().height()
            painter.drawText(QPointF(pos.x - 7 - tw, pos.y + 7 + fh), pos.label)
        else:
            # 上行反画 / 下行正画 → 车次号在右上
            painter.drawText(QPointF(pos.x + 7, pos.y - 7), pos.label)

        painter.restore()
