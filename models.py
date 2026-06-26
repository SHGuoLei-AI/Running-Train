import math
import json
import sqlite3


class TrainGraph:
    """列车运行图类"""
    def __init__(self, name, length=1000, width=600, scale=1, **kwargs):
        self.name = name
        self.length = length
        self.width = width
        self.scale = scale
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.train_paths = []

    def add_train_path(self, path):
        self.train_paths.append(path)

    def get_all_tracks(self):
        tracks = []
        for path in self.train_paths:
            if not path.hidden:
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
    def __init__(self, length, deflection, head_station="", tail_station="",
                 draw_head=True, draw_tail=False, start_point=(0, 0), label_flip=0,
                 up_direction="N", down_direction="S", is_down=1, **kwargs):
        self.length = length
        self.deflection = deflection
        self.head_station = head_station
        self.tail_station = tail_station
        self.draw_head = draw_head
        self.draw_tail = draw_tail
        self.start_point = start_point
        self.parent_angle = 0.0
        self.label_flip = label_flip
        self.up_direction = up_direction
        self.down_direction = down_direction
        self.is_down = is_down
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


def load_train_graph_from_json(json_file_path):
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    g = data['TrainGraph']
    train_graph = TrainGraph(name=g['name'], length=g['length'], width=g['width'],
                             scale=g.get('scale', 1))
    for p_data in g['paths']:
        path = RailwayPath(path_id=p_data['id'], name=p_data['name'],
                           start_x=p_data['start_x'], start_y=p_data['start_y'],
                           angle=p_data.get('angle', 0.0), hidden=p_data.get('hidden', False))
        for t_data in p_data['tracks']:
            path.add_track(RailwayTrack(
                length=t_data['length'], deflection=t_data['deflection'],
                head_station=t_data.get('head_station', ""),
                tail_station=t_data.get('tail_station', ""),
                draw_head=t_data.get('draw_start', True),
                draw_tail=t_data.get('draw_end', False),
                up_direction=t_data.get('up_direction', 'N'),
                down_direction=t_data.get('down_direction', 'S'),
                is_down=t_data.get('is_down', 1)))
        train_graph.add_train_path(path)
    return train_graph


def save_train_graph_to_json(train_graph, file_path, routes=None, route_stations=None):
    """Save TrainGraph to JSON. Optionally include routes and route_stations."""
    data = {
        "TrainGraph": {
            "date": "",
            "author": "",
            "name": train_graph.name,
            "length": train_graph.length,
            "width": train_graph.width,
            "scale": train_graph.scale,
            "paths": [
                {
                    "id": p.id,
                    "name": p.name,
                    "start_x": p.start_point[0],
                    "start_y": p.start_point[1],
                    "angle": p.angle,
                    "hidden": p.hidden,
                    "tracks": [
                        {
                            "head_station": t.head_station,
                            "tail_station": t.tail_station,
                            "length": t.length,
                            "deflection": t.deflection,
                            "draw_start": t.draw_head,
                            "draw_end": t.draw_tail,
                            "label_flip": getattr(t, 'label_flip', 0),
                            "up_direction": getattr(t, 'up_direction', 'N') or 'N',
                            "down_direction": getattr(t, 'down_direction', 'S') or 'S',
                            "is_down": getattr(t, 'is_down', 1) if getattr(t, 'is_down', None) is not None else 1,
                        }
                        for t in p.tracks
                    ]
                }
                for p in train_graph.train_paths
            ]
        }
    }
    if routes is not None:
        data["TrainGraph"]["routes"] = routes
    if route_stations is not None:
        data["TrainGraph"]["route_stations"] = route_stations
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _resolve_db(db):
    """Accept either a Connection or a path string, return (conn, own_conn)."""
    if isinstance(db, str):
        return sqlite3.connect(db), True
    return db, False


def load_train_graph_from_db(db, graph_name=None):
    """Load TrainGraph from running_train.db.

    db: sqlite3.Connection or file path string.
    graph_name: ignored (kept for backward compat); always loads the single graph.
    """
    conn, own = _resolve_db(db)
    try:
        g = conn.execute(
            'SELECT name, length, width, scale, default_scale, default_speed, '
            'rg_version, kl_version, cc_version, author '
            'FROM train_graph LIMIT 1').fetchone()
        if not g:
            raise ValueError('No train_graph found in database')
        train_graph = TrainGraph(
            name=g[0], length=g[1], width=g[2], scale=g[3],
            default_scale=g[4] if g[4] is not None else g[3],
            default_speed=g[5] if g[5] is not None else 1.0,
            rg_version=g[6] if len(g) > 6 and g[6] is not None else 1,
            kl_version=g[7] if len(g) > 7 and g[7] is not None else '',
            cc_version=g[8] if len(g) > 8 and g[8] is not None else '',
            author=g[9] if len(g) > 9 and g[9] is not None else '')

        paths = conn.execute(
            'SELECT id, name, kl_line_name, start_x, start_y, angle, hidden '
            'FROM railway_path ORDER BY sort_order, id').fetchall()

        for prow in paths:
            pid, pname, kl, sx, sy, angle, hidden = prow
            path_id = str(pid)
            kw = {}
            if kl:
                kw['kl_line_name'] = kl
            path = RailwayPath(path_id=path_id, name=pname,
                               start_x=sx, start_y=sy,
                               angle=angle or 0.0, hidden=bool(hidden), **kw)

            tracks = conn.execute(
                'SELECT head_station, tail_station, length, deflection, '
                'draw_head, draw_tail, label_flip, up_direction, down_direction, '
                'is_down '
                'FROM railway_track WHERE path_id=? ORDER BY seq',
                (pid,)).fetchall()

            for hs, ts, length, deflection, dh, dt, lf, ud, dd, idn in tracks:
                path.add_track(RailwayTrack(
                    length=length, deflection=deflection or 0,
                    head_station=hs or '', tail_station=ts or '',
                    draw_head=bool(dh), draw_tail=bool(dt),
                    label_flip=int(lf or 0),
                    up_direction=ud or 'N',
                    down_direction=dd or 'S',
                    is_down=int(idn) if idn is not None else 1))

            train_graph.add_train_path(path)

        return train_graph
    finally:
        if own:
            conn.close()


def save_train_graph_to_db(train_graph, db):
    """Save TrainGraph to running_train.db (full replace within a transaction).

    db: sqlite3.Connection or file path string.
    """
    conn, own = _resolve_db(db)
    try:
        graph_name = train_graph.name

        conn.execute('BEGIN')
        conn.execute('DELETE FROM railway_track')
        conn.execute('DELETE FROM railway_path')

        conn.execute(
            'INSERT OR REPLACE INTO train_graph '
            '(name, length, width, scale, default_scale, default_speed, '
            'rg_version, kl_version, cc_version, author) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)',
            (train_graph.name, train_graph.length, train_graph.width, train_graph.scale,
             getattr(train_graph, 'default_scale', train_graph.scale) or train_graph.scale,
             getattr(train_graph, 'default_speed', 1.0) or 1.0,
             getattr(train_graph, 'rg_version', 1) or 1,
             getattr(train_graph, 'kl_version', '') or '',
             getattr(train_graph, 'cc_version', '') or '',
             getattr(train_graph, 'author', '') or ''))

        for sort_order, path in enumerate(train_graph.train_paths):
            kl = getattr(path, 'kl_line_name', '') or ''
            cur = conn.execute(
                'INSERT INTO railway_path '
                '(name, kl_line_name, start_x, start_y, angle, hidden, sort_order) '
                'VALUES (?,?,?,?,?,?,?)',
                (path.name, kl,
                 path.start_point[0], path.start_point[1],
                 path.angle, 1 if path.hidden else 0, sort_order))
            path_db_id = cur.lastrowid

            for seq, track in enumerate(path.tracks):
                conn.execute(
                    'INSERT INTO railway_track '
                    '(path_id, seq, head_station, tail_station, length, deflection, '
                    'draw_head, draw_tail, label_flip, up_direction, down_direction, is_down) '
                    'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (path_db_id, seq,
                     track.head_station, track.tail_station,
                     track.length, track.deflection,
                     1 if track.draw_head else 0,
                     1 if track.draw_tail else 0,
                     getattr(track, 'label_flip', 0),
                     getattr(track, 'up_direction', 'N') or 'N',
                     getattr(track, 'down_direction', 'S') or 'S',
                     getattr(track, 'is_down', 1) if getattr(track, 'is_down', None) is not None else 1))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def list_graphs_in_db(db):
    """Return list of (name,) tuples for all train_graphs in the DB."""
    conn, own = _resolve_db(db)
    try:
        return conn.execute('SELECT name FROM train_graph ORDER BY name').fetchall()
    finally:
        if own:
            conn.close()
