import math
import json


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
                 draw_head=True, draw_tail=False, start_point=(0, 0), **kwargs):
        self.length = length
        self.deflection = deflection
        self.head_station = head_station
        self.tail_station = tail_station
        self.draw_head = draw_head
        self.draw_tail = draw_tail
        self.start_point = start_point
        self.parent_angle = 0.0
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
                draw_tail=t_data.get('draw_end', False)))
        train_graph.add_train_path(path)
    return train_graph


def save_train_graph_to_json(train_graph, file_path):
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
                        }
                        for t in p.tracks
                    ]
                }
                for p in train_graph.train_paths
            ]
        }
    }
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
