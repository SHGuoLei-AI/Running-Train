"""列车运行模拟核心模块

RouteTrackIndex: 经由站序→图内 track 序列预计算映射
TrainPositioner: 车次→train_route_matches→画布位置（时间比例线性插值）
SimulationClock: 模拟时钟 0-1439 分钟循环
TrainRenderer: 列车绘制（圆点 + 方向标签）
"""
import math
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
    is_down: int = 1  # track 头→尾 方向是否为下行（1=下行，0=上行）


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
    direction: str = "N"  # 标签罗盘方向（N/S/E/W）
    train_name: str = ""  # 完整车次名（如 C801/C804）


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
                    is_down=getattr(track, 'is_down', 1) if getattr(track, 'is_down', None) is not None else 1,
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
# RouteTrackIndex
# ——————————————————————————————————————

class RouteTrackIndex:
    """经由站序 → 图内 track 序列的预计算映射。

    从 rg.db 的经由数据 + TrainGraph 的轨道几何，预先计算
    每条经由上任意两个连续站序之间的图内 track 序列。
    """

    def __init__(self):
        # (route_id, from_seq, to_seq) → list[TrackInfo]
        self._pair_tracks: dict[tuple, list[TrackInfo]] = {}
        # route_id → [(seq, station_name, line_name, cum_km), ...]
        self._route_stations: dict[int, list[tuple]] = {}
        # route_id → {station_name: seq}
        self._route_stn_seq: dict[int, dict[str, int]] = {}
        # 隐藏 path 的 id 集合（参与匹配但不画列车）
        self.hidden_path_ids: set[str] = set()

    @classmethod
    def build(cls, rg_conn, train_graph) -> "RouteTrackIndex":
        idx = cls()
        scale = train_graph.scale

        # — 1. 构建 per-path 索引：path_id → {station: track_index} —
        path_stations: dict[str, dict[str, int]] = {}   # path_id → {stn: ti}
        path_tracks: dict[str, list[TrackInfo]] = {}    # path_id → [TrackInfo]
        line_paths: dict[str, list[str]] = {}            # kl_line_name → [path_id]

        for path in train_graph.train_paths:
            # 隐藏的 path 也参与经由匹配，只是画布上不画
            if path.hidden:
                idx.hidden_path_ids.add(path.id)
            kl = getattr(path, 'kl_line_name', '') or ''
            pid = path.id

            stn_map: dict[str, int] = {}
            track_infos: list[TrackInfo] = []

            for ti, track in enumerate(path.tracks):
                sx, sy = track.start_point
                ex, ey = track.end_point()
                info = TrackInfo(
                    head_station=track.head_station,
                    tail_station=track.tail_station,
                    x1=int(sx * scale), y1=int(sy * scale),
                    x2=int(ex * scale), y2=int(ey * scale),
                    length_km=track.length,
                    angle_rad=math.radians(track.actual_angle),
                    path_code=str(pid),
                    is_down=getattr(track, 'is_down', 1) if getattr(track, 'is_down', None) is not None else 1,
                )
                track_infos.append(info)
                stn_map[track.head_station] = ti

            if path.tracks:
                stn_map[path.tracks[-1].tail_station] = len(path.tracks)

            path_stations[pid] = stn_map
            path_tracks[pid] = track_infos
            if kl:
                line_paths.setdefault(kl, []).append(pid)

        # — 2. 加载所有经由站序 —
        for (rid,) in rg_conn.execute('SELECT id FROM routes ORDER BY id').fetchall():
            sts = rg_conn.execute(
                'SELECT seq, station_name, line_name, cum_distance '
                'FROM route_stations WHERE route_id=? ORDER BY seq', (rid,)
            ).fetchall()
            idx._route_stations[rid] = sts
            stn_seq: dict[str, int] = {}
            for seq, sn, ln, cd in sts:
                stn_seq[sn] = seq
            idx._route_stn_seq[rid] = stn_seq

            if len(sts) < 2:
                continue

            # — 3. 为每对连续站序找图内 track —
            for i in range(len(sts) - 1):
                seq_a, stn_a, line_a, _ = sts[i]
                seq_b, stn_b, line_b, _ = sts[i + 1]

                pids = line_paths.get(line_a, [])
                found = False
                for pid in pids:
                    stn_idx = path_stations.get(pid, {})
                    tracks = path_tracks.get(pid, [])
                    ia = stn_idx.get(stn_a)
                    ib = stn_idx.get(stn_b)
                    if ia is not None and ib is not None and ia != ib:
                        sub = (tracks[ia:ib] if ia < ib
                               else list(reversed(tracks[ib:ia])))
                        if sub:
                            idx._pair_tracks[(rid, seq_a, seq_b)] = sub
                            found = True
                            break

        return idx

    def get_tracks_between(self, route_id: int,
                           from_station: str, to_station: str
                           ) -> Optional[list[TrackInfo]]:
        """获取经由上两站之间（含中间所有非停站站）的全部 track 序列。

        Returns: track 列表（按行进顺序），或 None（映射缺失）。
        """
        stn_seq = self._route_stn_seq.get(route_id, {})
        seq_a = stn_seq.get(from_station)
        seq_b = stn_seq.get(to_station)
        if seq_a is None or seq_b is None:
            return None

        all_tracks: list[TrackInfo] = []
        rng = range(seq_a, seq_b) if seq_a < seq_b else range(seq_b, seq_a)
        for s in rng:
            key = (route_id, s, s + 1)
            pair = self._pair_tracks.get(key)
            if pair is None:
                # 跨线接续站（同站不同线，距离为0）允许跳过
                # sts 按 seq 排序，索引 = seq-1
                sts = self._route_stations.get(route_id, [])
                idx_a = s - 1   # seq s 在列表中的索引
                idx_b = s        # seq s+1 在列表中的索引
                if 0 <= idx_a < len(sts) and 0 <= idx_b < len(sts):
                    if sts[idx_a][1] == sts[idx_b][1]:
                        continue  # 跳过接续站对
                return None  # 非接续站的缺失 → 真正失败
            all_tracks.extend(pair)

        if seq_a > seq_b:
            all_tracks = list(reversed(all_tracks))
        return all_tracks if all_tracks else None

    def get_route_station_distance(self, route_id: int, station_name: str) -> Optional[float]:
        """获取经由上某站的累计里程。"""
        for seq, sn, ln, cd in self._route_stations.get(route_id, []):
            if sn == station_name:
                return cd
        return None


# ——————————————————————————————————————
# TrainPositioner
# ——————————————————————————————————————

TRACK_OFFSET = 10  # 上行/下行距中心线的像素偏移量

DIRECTION_VECTORS = {
    'N': (0, -1), 'S': (0, 1), 'E': (1, 0), 'W': (-1, 0),
}
DIRECTION_LABELS = ['N', 'E', 'S', 'W']


def _perpendicular_offset(angle_rad: float, sign: int) -> tuple[float, float]:
    """垂直轨道方向的偏移量（sign=+1=屏幕上方/上行方向）"""
    return -sign * TRACK_OFFSET * -math.sin(angle_rad), -sign * TRACK_OFFSET * math.cos(angle_rad)


def _label_direction(angle_rad: float, p_sign: int) -> str:
    """根据轨道角度和偏移符号自动计算车次号方向（N/E/S/W）。

    轨道角度≈0°且下行在上→下行N上行S；
    轨道角度≈180°且下行在下→下行S上行N；
    轨道角度≈90°→下行E上行W；
    轨道角度≈270°→下行W上行E。
    """
    dx = p_sign * TRACK_OFFSET * math.sin(angle_rad)
    dy = -p_sign * TRACK_OFFSET * math.cos(angle_rad)
    if abs(dx) >= abs(dy):
        return 'E' if dx > 0 else 'W'
    else:
        return 'N' if dy < 0 else 'S'



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


def _train_is_down_on_track(track: TrackInfo, is_forward: bool) -> bool:
    """判断列车在给定 track 上的运行方向是否为下行。

    track.is_down 表示 track 头→尾 方向是否为下行。
    is_forward=True 表示列车沿 track 头→尾 方向运行。
    """
    return bool(track.is_down) if is_forward else not bool(track.is_down)


def _perpendicular_sign(train_is_down: bool) -> int:
    """上下行 → 垂直偏移符号。
    上行 → -1（靠左/轨道上方），下行 → +1（靠右/轨道下方）。
    """
    return 1 if train_is_down else -1





class TrainPositioner:
    """基于经由匹配数据的列车定位器。

    使用 train_route_matches 确定车次在图内的区段，
    通过 RouteTrackIndex 将经由站序映射到画布 track 坐标。
    仅绘制匹配到经由的区段（matched），图外区段（unmatched）不画。
    """

    def __init__(self, rt_db_path: str, rg_conn, train_graph):
        self._trains: dict[str, list[TrainStop]] = {}       # train_name → 有序停站
        self._matches: dict[str, list[dict]] = {}           # train_name → 匹配段列表
        self._route_index = RouteTrackIndex.build(rg_conn, train_graph)
        self._load(rt_db_path)

    # ── 加载 ────────────────────────────────────────────

    def _load(self, db_path: str):
        """从 rt.db 加载车次停站和经由匹配数据。"""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            # 加载停站
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

            # 加载匹配段（仅 matched）
            match_rows = conn.execute(
                'SELECT train_name, seg_start_seq, seg_end_seq, route_id, route_name '
                'FROM train_route_matches '
                'WHERE match_type=\'matched\' '
                'ORDER BY train_name, seg_start_seq'
            ).fetchall()

            for mr in match_rows:
                tn = mr['train_name']
                rid = mr['route_id']
                rname = mr['route_name'] or ''
                # 多经由匹配（route_id 为 NULL/0，route_name 如 R11+R9）需拆分
                if (rid is None or rid == 0) and '+' in rname:
                    expanded = self._expand_multi_route(
                        tn, mr['seg_start_seq'], mr['seg_end_seq'],
                        rname, self._trains.get(tn, []))
                    for exp_seg in expanded:
                        self._matches.setdefault(tn, []).append(exp_seg)
                elif rid is not None and rid != 0:
                    seg = {
                        'start_seq': mr['seg_start_seq'],
                        'end_seq': mr['seg_end_seq'],
                        'route_id': rid,
                    }
                    self._matches.setdefault(tn, []).append(seg)
        finally:
            conn.close()

    # ── 定位 ────────────────────────────────────────────

    def position(self, train_name: str, minute: float) -> list[TrainPosition]:
        """计算一趟车在指定时刻的全部画布位置（多日行程可返回多个实例）。

        仅当列车位于匹配段内时才返回位置（否则视为图外，不画）。
        始发站开车前5分钟出现，终到站到达后5分钟消失。
        """
        stops = self._trains.get(train_name)
        if not stops or len(stops) < 2:
            return []

        first_dep = stops[0].dep_min
        last_arr = stops[-1].arr_min
        if first_dep is None or last_arr is None:
            return []

        # — 归一化时间（单调递增，自动处理多日行程）—
        norm: list[tuple[Optional[int], Optional[int]]] = []
        prev = first_dep
        for s in stops:
            a = s.arr_min
            d = s.dep_min
            if a is not None:
                while a < prev:
                    a += 1440
                prev = a
            if d is not None:
                while d < prev:
                    d += 1440
                prev = d
            norm.append((a, d))

        norm_last_arr = norm[-1][0]

        # — 找最小的 T ≥ first_dep − 5 —
        T = minute
        while T < first_dep - 5:
            T += 1440

        # — 遍历所有可能的日期偏移（每1440分钟一个实例）—
        result = []
        while norm_last_arr is not None and T <= norm_last_arr + 5:
            pos = self._position_at(stops, norm, train_name, T)
            if pos is not None:
                result.append(pos)
            T += 1440

        return result

    def _position_at(self, stops: list[TrainStop],
                     norm: list[tuple[Optional[int], Optional[int]]],
                     train_name: str, T: int) -> Optional[TrainPosition]:
        """在归一化时刻 T 定位列车。"""
        # — 找到 T 所在的停站区间 —
        for i in range(len(stops)):
            arr_i, dep_i = norm[i]

            # 停站中？
            if arr_i is not None and dep_i is not None and arr_i <= T <= dep_i:
                return self._at_station(stops, i, train_name)

            # 区间运行？
            if i < len(stops) - 1:
                arr_next = norm[i + 1][0]
                if dep_i is not None and arr_next is not None and dep_i < T < arr_next:
                    return self._running(stops, i, train_name, T, dep_i, arr_next)

        return None

    # ── 停站定位 ────────────────────────────────────────

    def _on_hidden_path(self, tracks: list[TrackInfo]) -> bool:
        """检查 track 序列是否全部在隐藏 path 上（全部隐藏才跳过）。"""
        if not tracks:
            return False
        for t in tracks:
            if t.path_code not in self._route_index.hidden_path_ids:
                return False  # 至少有一条可见 track → 不跳过
        return True  # 全部隐藏

    def _at_station(self, stops: list[TrainStop], i: int, train_name: str) -> Optional[TrainPosition]:
        """列车停在 stops[i]，在对应图内 track 的站端坐标。"""
        label = stops[i].segment_train_no or train_name
        color = train_color(train_name)

        # 找到包含此站的匹配段（端站允许命中）
        seg = self._find_containing_segment(train_name, i, inclusive_end=True)
        if seg is None:
            return None

        is_seg_end = (i == seg['end_seq'])

        if i >= len(stops) - 1 or is_seg_end:
            # 终到站 或 匹配段末站：取上一段的末端 track
            tracks = self._get_stop_pair_tracks(stops, i - 1, train_name, seg)
            if not tracks:
                return None
            last_track = tracks[-1]
            if stops[i].station_name == last_track.tail_station:
                x, y = last_track.x2, last_track.y2
                is_forward = True
            else:
                x, y = last_track.x1, last_track.y1
                is_forward = False

            train_is_down = _train_is_down_on_track(last_track, is_forward)
            p_sign = _perpendicular_sign(train_is_down)
            dx, dy = _perpendicular_offset(last_track.angle_rad, p_sign)
            direction = _label_direction(last_track.angle_rad, p_sign)
            return TrainPosition(x=x + dx, y=y + dy, label=label, color=color,
                                 direction=direction, train_name=train_name)

        # 一般停站：取下一段的起始 track
        tracks = self._get_stop_pair_tracks(stops, i, train_name, seg)
        if not tracks:
            return None

        first_track = tracks[0]
        if stops[i].station_name == first_track.head_station:
            x, y = first_track.x1, first_track.y1
            is_forward = True
        else:
            x, y = first_track.x2, first_track.y2
            is_forward = False

        train_is_down = _train_is_down_on_track(first_track, is_forward)
        p_sign = _perpendicular_sign(train_is_down)
        dx, dy = _perpendicular_offset(first_track.angle_rad, p_sign)
        direction = _label_direction(first_track.angle_rad, p_sign)

        return TrainPosition(x=x + dx, y=y + dy, label=label, color=color,
                             direction=direction, train_name=train_name)

    # ── 区间运行定位 ────────────────────────────────────

    def _running(self, stops: list[TrainStop], i: int, train_name: str,
                 T: float, dep: int, arr: int) -> Optional[TrainPosition]:
        """列车在 stops[i]→stops[i+1] 区间运行。"""
        seg_dist = stops[i + 1].dist_km - stops[i].dist_km
        if seg_dist <= 0:
            return self._at_station(stops, i, train_name)

        seg = self._find_containing_segment(train_name, i)
        if seg is None:
            return None

        tracks = self._get_stop_pair_tracks(stops, i, train_name, seg)
        if not tracks:
            return None

        label = stops[i].segment_train_no or train_name
        nxt_seg_no = stops[i + 1].segment_train_no if i + 1 < len(stops) else None

        time_ratio = (T - dep) / (arr - dep)
        traveled = time_ratio * seg_dist

        # 沿 track 序列逐段定位
        entry_stn = stops[i].station_name
        acc = 0.0
        hidden_ids = self._route_index.hidden_path_ids
        for ti, track in enumerate(tracks):
            # 复车次换号检测：跨 path 且下一站车次号不同时切换
            if ti > 0 and track.path_code != tracks[ti - 1].path_code:
                if nxt_seg_no and nxt_seg_no != stops[i].segment_train_no:
                    label = nxt_seg_no

            tk_len = track.length_km
            is_last = (ti == len(tracks) - 1)
            is_forward = (entry_stn == track.head_station)
            exit_stn = track.tail_station if is_forward else track.head_station

            # 基于 track 方向判定上下行
            train_is_down = _train_is_down_on_track(track, is_forward)
            p_sign = _perpendicular_sign(train_is_down)

            if traveled <= acc + tk_len or is_last:
                # 当前 track 属于隐藏 path → 列车不可见
                if track.path_code in hidden_ids:
                    return None

                local = traveled - acc
                ratio = local / tk_len if tk_len > 0 else 0.0
                if not is_forward:
                    ratio = 1.0 - ratio
                ratio = max(0.0, min(1.0, ratio))

                x = track.x1 + ratio * (track.x2 - track.x1)
                y = track.y1 + ratio * (track.y2 - track.y1)
                dx, dy = _perpendicular_offset(track.angle_rad, p_sign)
                direction = _label_direction(track.angle_rad, p_sign)

                return TrainPosition(x=x + dx, y=y + dy, label=label,
                                     color=train_color(train_name),
                                     direction=direction, train_name=train_name)

            acc += tk_len
            entry_stn = exit_stn

        # fallback
        last_track = tracks[-1]
        if last_track.path_code in hidden_ids:
            return None
        is_forward = (entry_stn == last_track.tail_station)
        train_is_down = _train_is_down_on_track(last_track, is_forward)
        p_sign = _perpendicular_sign(train_is_down)
        dx, dy = _perpendicular_offset(last_track.angle_rad, p_sign)
        direction = _label_direction(last_track.angle_rad, p_sign)
        return TrainPosition(x=last_track.x2 + dx, y=last_track.y2 + dy,
                             label=label, color=train_color(train_name),
                             direction=direction, train_name=train_name)

    # ── 辅助 ────────────────────────────────────────────

    def _find_containing_segment(self, train_name: str, stop_i: int,
                                  inclusive_end: bool = False) -> Optional[dict]:
        """找到包含 stop_i 的匹配段。inclusive_end=True 时允许端站命中。"""
        for seg in self._matches.get(train_name, []):
            end = seg['end_seq']
            if inclusive_end:
                if seg['start_seq'] <= stop_i <= end:
                    return seg
            else:
                if seg['start_seq'] <= stop_i < end:
                    return seg
        return None

    def _get_stop_pair_tracks(self, stops: list[TrainStop], i: int,
                              train_name: str, seg: dict
                              ) -> Optional[list[TrackInfo]]:
        """获取两停站之间的全部 track 序列（含中间非停站的经由站）。

        支持多经由拼接：seg 可含 route_ids 列表 + junction_station，
        当单条经由无法覆盖整个停站对时，尝试在接续站处拼接两条经由的 track。
        """
        a = stops[i].station_name
        b = stops[i + 1].station_name
        route_id = seg.get('route_id', 0)

        if 'route_ids' in seg and route_id == 0:
            # 多经由拼接匹配：先试分别查，再试接续站拼接
            rids = seg['route_ids']
            junction = seg.get('junction_station', '')
            for rid in rids:
                tracks = self._route_index.get_tracks_between(rid, a, b)
                if tracks:
                    return tracks
            if junction:
                tracks_a = self._route_index.get_tracks_between(rids[0], a, junction)
                tracks_b = self._route_index.get_tracks_between(rids[1], junction, b)
                if tracks_a and tracks_b:
                    return tracks_a + tracks_b
            return None

        return self._route_index.get_tracks_between(route_id, a, b)

    def _expand_multi_route(self, train_name: str, start_seq: int, end_seq: int,
                             route_name: str, stops: list[TrainStop]) -> list[dict]:
        """将多经由匹配（R11+R9）拆分为两个单独经由段。

        在停站列表中找接续站（出现在两条经由中的车站），以此拆分。
        如 K9756：乌鲁木齐→库尔勒(R11) + 库尔勒→若羌(R9)。
        """
        import re
        parts = re.findall(r'R(\d+)', route_name)
        if len(parts) < 2:
            return [{'start_seq': start_seq, 'end_seq': end_seq, 'route_id': 0}]

        rid_a = int(parts[0])
        rid_b = int(parts[1])
        sts_a = self._route_index._route_stations.get(rid_a, [])
        sts_b = self._route_index._route_stations.get(rid_b, [])
        if not sts_a or not sts_b:
            return [{'start_seq': start_seq, 'end_seq': end_seq, 'route_id': 0}]

        names_a = {s[1] for s in sts_a}
        names_b = {s[1] for s in sts_b}

        # 在停站中找同时出现在两条经由中的接续站
        jn_seq = None
        for seq in range(start_seq, end_seq + 1):
            stn = stops[seq].station_name
            if stn in names_a and stn in names_b:
                jn_seq = seq
                break

        if jn_seq is None or jn_seq == start_seq or jn_seq == end_seq:
            # 回退：从途经站中找接续站（即使车次不在此停站）
            common = sorted(names_a & names_b)
            if common:
                return [{'start_seq': start_seq, 'end_seq': end_seq,
                         'route_id': 0, 'route_ids': [rid_a, rid_b],
                         'junction_station': common[0]}]
            return [{'start_seq': start_seq, 'end_seq': end_seq, 'route_id': 0}]

        result = []
        if jn_seq > start_seq:
            result.append({'start_seq': start_seq, 'end_seq': jn_seq, 'route_id': rid_a})
        if jn_seq < end_seq:
            result.append({'start_seq': jn_seq, 'end_seq': end_seq, 'route_id': rid_b})
        return result if result else [
            {'start_seq': start_seq, 'end_seq': end_seq, 'route_id': 0}]

    def visible_trains(self, minute: float) -> list[TrainPosition]:
        """获取指定时刻所有可见列车位置（多日车次可出现多次）。"""
        result = []
        for train_name in self._trains:
            result.extend(self.position(train_name, minute))
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

    def step(self, minutes: int):
        """步进 N 分钟（暂停时使用）"""
        self.current_minute += minutes
        while self.current_minute >= 1440.0:
            self.current_minute -= 1440.0
        while self.current_minute < 0.0:
            self.current_minute += 1440.0
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
        """画一个列车：5px 实心圆 + 车次号（标签位置由轨道罗盘方向决定）"""
        painter.save()

        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(pos.color)
        painter.drawEllipse(QPointF(pos.x, pos.y), 4, 4)

        font = painter.font()
        font.setPixelSize(8)
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        tw = painter.fontMetrics().horizontalAdvance(pos.label)
        fh = painter.fontMetrics().height()

        # 标签位置：根据罗盘方向放置在圆点旁边
        vec = DIRECTION_VECTORS.get(pos.direction, DIRECTION_VECTORS['N'])
        dx, dy = vec[0], vec[1]
        gap = 7  # 圆点边缘到标签的距离

        # 锚点：从圆心沿方向偏移
        ax = pos.x + dx * (5 + gap)
        ay = pos.y + dy * (5 + gap)

        # 根据方向分量对齐文字
        if dx > 0.01:
            lx = ax
        elif dx < -0.01:
            lx = ax - tw
        else:
            lx = ax - tw / 2

        if dy > 0.01:
            ly = ay
        elif dy < -0.01:
            ly = ay + fh / 3
        else:
            ly = ay + fh / 3

        painter.drawText(QPointF(lx, ly), pos.label)

        painter.restore()
