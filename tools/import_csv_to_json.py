import argparse
import csv
import datetime
import json
import os
import sqlite3

ENCODINGS = ['utf-8-sig', 'utf-8', 'gbk', 'cp936', 'latin1']

PATH_FIELD_PATTERNS = {
    'path_id': ['pathid', '线路id', 'lineid', 'id'],
    'name': ['name', '线路', '线路名', '线路名称', 'line', 'line_name'],
    'start_x': ['startx', 'x'],
    'start_y': ['starty', 'y'],
    'angle': ['角度', 'angle'],
    'hidden': ['隐藏', 'hidden'],
}

SECTION_FIELD_PATTERNS = {
    'path_id': ['pathid', '线路id', 'lineid', 'id'],
    'head_station': ['起点', 'head', 'source', 'from'],
    'tail_station': ['终点', 'tail', 'destination', 'to'],
    'length': ['长度', 'length'],
    'deflection': ['偏转', 'deflection'],
    'draw_start': ['画起点', 'drawstart'],
    'draw_end': ['画终点', 'drawend'],
}

PATH_KEYS = {'path_id', 'name', 'start_x', 'start_y', 'angle', 'hidden'}
TRACK_KEYS = {'length', 'deflection', 'head_station', 'tail_station', 'draw_start', 'draw_end'}


def normalize_header(header):
    return header.strip().lower().replace(' ', '').replace('_', '')


def parse_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    if text == '':
        return ''
    lower = text.lower()
    if lower in ('true', 'false'):
        return lower == 'true'
    try:
        if '.' in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def load_csv_rows(csv_path):
    for encoding in ENCODINGS:
        try:
            with open(csv_path, 'r', encoding=encoding, newline='') as f:
                reader = csv.DictReader(f)
                rows = [row for row in reader]
                if reader.fieldnames:
                    return rows, reader.fieldnames, encoding
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    raise ValueError(f'无法读取 CSV 文件: {csv_path}')


def find_header_key(fieldnames, patterns):
    normalized = {normalize_header(name): name for name in fieldnames if name is not None}
    # First try exact matches to avoid a general pattern matching a more specific header.
    for pattern in patterns:
        norm_pattern = normalize_header(pattern)
        if norm_pattern in normalized:
            return normalized[norm_pattern]
    # Fallback to substring matching for less specific patterns.
    for pattern in patterns:
        norm_pattern = normalize_header(pattern)
        for norm, original in normalized.items():
            if norm_pattern in norm:
                return original
    return None


def is_path_field_header(header):
    if header is None:
        return False
    normalized = normalize_header(header)
    for patterns in PATH_FIELD_PATTERNS.values():
        for pattern in patterns:
            if pattern in normalized:
                return True
    return False


def get_value(row, key):
    if key is None:
        return None
    return parse_value(row.get(key, ''))


def build_train_graph(line_rows, section_rows, line_headers, section_headers, default_name):
    path_id_key = find_header_key(line_headers, PATH_FIELD_PATTERNS['path_id'])
    if path_id_key is None:
        raise ValueError('无法在线路 CSV 中找到路径 ID 列。')

    name_key = find_header_key(line_headers, PATH_FIELD_PATTERNS['name'])
    start_x_key = find_header_key(line_headers, PATH_FIELD_PATTERNS['start_x'])
    start_y_key = find_header_key(line_headers, PATH_FIELD_PATTERNS['start_y'])
    angle_key = find_header_key(line_headers, PATH_FIELD_PATTERNS['angle'])
    hidden_key = find_header_key(line_headers, PATH_FIELD_PATTERNS['hidden'])

    section_path_id_key = find_header_key(section_headers, SECTION_FIELD_PATTERNS['path_id'])
    if section_path_id_key is None:
        raise ValueError('无法在区间 CSV 中找到路径 ID 列。')
    head_key = find_header_key(section_headers, SECTION_FIELD_PATTERNS['head_station'])
    tail_key = find_header_key(section_headers, SECTION_FIELD_PATTERNS['tail_station'])
    length_key = find_header_key(section_headers, SECTION_FIELD_PATTERNS['length'])
    deflection_key = find_header_key(section_headers, SECTION_FIELD_PATTERNS['deflection'])
    draw_start_key = find_header_key(section_headers, SECTION_FIELD_PATTERNS['draw_start'])
    draw_end_key = find_header_key(section_headers, SECTION_FIELD_PATTERNS['draw_end'])

    paths = []
    path_index = {}

    def create_path_from_row(row):
        path_id = get_value(row, path_id_key)
        if path_id in path_index:
            return path_index[path_id]

        path = {
            'id': path_id,
            'name': get_value(row, name_key) if name_key else str(path_id),
            'start_x': get_value(row, start_x_key) if start_x_key else 0,
            'start_y': get_value(row, start_y_key) if start_y_key else 0,
            'angle': get_value(row, angle_key) if angle_key else 0.0,
            'hidden': get_value(row, hidden_key) if hidden_key is not None else False,
            'tracks': []
        }
        for key, value in row.items():
            if key in {path_id_key, name_key, start_x_key, start_y_key, angle_key, hidden_key}:
                continue
            if is_path_field_header(key):
                continue
            path[key] = parse_value(value)
        paths.append(path)
        path_index[path_id] = path
        return path

    for row in line_rows:
        create_path_from_row(row)

    def create_track_from_row(row):
        track = {
            'head_station': get_value(row, head_key) if head_key else '',
            'tail_station': get_value(row, tail_key) if tail_key else '',
            'length': get_value(row, length_key) if length_key else 0,
            'deflection': get_value(row, deflection_key) if deflection_key else 0,
        }
        if draw_start_key is not None:
            track['draw_start'] = get_value(row, draw_start_key)
        if draw_end_key is not None:
            track['draw_end'] = get_value(row, draw_end_key)
        for key, value in row.items():
            if key not in {section_path_id_key, head_key, tail_key, length_key, deflection_key, draw_start_key, draw_end_key}:
                track[key] = parse_value(value)
        return track

    for row in section_rows:
        path_id = get_value(row, section_path_id_key)
        if path_id not in path_index:
            default_path = {
                'id': path_id,
                'name': str(path_id),
                'start_x': 0,
                'start_y': 0,
                'angle': 0.0,
                'hidden': False,
                'tracks': []
            }
            path_index[path_id] = default_path
            paths.append(default_path)
        path = path_index[path_id]
        path['tracks'].append(create_track_from_row(row))

    return {
        'name': default_name,
        'paths': paths
    }


def write_graph_json(graph_path, graph_payload, preserve_metadata=None):
    if preserve_metadata is None:
        preserve_metadata = {}
    output = {
        'TrainGraph': {
            'date': datetime.date.today().isoformat(),
            'author': preserve_metadata.get('author', ''),
            'name': preserve_metadata.get('name', graph_payload['name']),
            'length': preserve_metadata.get('length', graph_payload.get('length', 0)),
            'width': preserve_metadata.get('width', graph_payload.get('width', 0)),
            'scale': preserve_metadata.get('scale', graph_payload.get('scale', 1.0)),
            'paths': graph_payload['paths'],
        }
    }
    output['TrainGraph'].update({k: v for k, v in preserve_metadata.items() if k not in output['TrainGraph']})
    with open(graph_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    return output


def load_existing_graph(graph_path):
    if not os.path.exists(graph_path):
        return {}
    with open(graph_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('TrainGraph', {})


def write_graph_db(db_path, graph_payload, preserve_metadata=None):
    """Write train graph to running_train.db."""
    if preserve_metadata is None:
        preserve_metadata = {}
    db = sqlite3.connect(db_path)

    graph_name = preserve_metadata.get('name', graph_payload['name'])
    graph_length = preserve_metadata.get('length', graph_payload.get('length', 0)) or 450
    graph_width = preserve_metadata.get('width', graph_payload.get('width', 0)) or 330
    graph_scale = preserve_metadata.get('scale', graph_payload.get('scale', 4)) or 4

    # Delete existing data for this graph
    db.execute(
        'DELETE FROM railway_track WHERE path_id IN '
        '(SELECT id FROM railway_path WHERE graph_name=?)', (graph_name,))
    db.execute('DELETE FROM railway_path WHERE graph_name=?', (graph_name,))
    db.execute('DELETE FROM train_graph WHERE name=?', (graph_name,))

    # Insert graph
    db.execute(
        'INSERT INTO train_graph (name, length, width, scale) VALUES (?,?,?,?)',
        (graph_name, graph_length, graph_width, graph_scale))

    # Insert paths and tracks
    for p_data in graph_payload['paths']:
        cur = db.execute(
            'INSERT INTO railway_path '
            '(graph_name, name, code, kl_line_name, start_x, start_y, angle, hidden) '
            'VALUES (?,?,?,?,?,?,?,?)',
            (graph_name,
             p_data.get('name', str(p_data['id'])),
             str(p_data['id']),
             p_data.get('kl_line_name', ''),
             p_data.get('start_x', 0),
             p_data.get('start_y', 0),
             p_data.get('angle', 0.0),
             1 if p_data.get('hidden', False) else 0))
        path_db_id = cur.lastrowid

        for seq, t_data in enumerate(p_data.get('tracks', [])):
            db.execute(
                'INSERT INTO railway_track '
                '(path_id, seq, head_station, tail_station, length, deflection, '
                'draw_head, draw_tail) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (path_db_id, seq,
                 t_data.get('head_station', ''),
                 t_data.get('tail_station', ''),
                 t_data.get('length', 0),
                 t_data.get('deflection', 0),
                 1 if t_data.get('draw_start', True) else 0,
                 1 if t_data.get('draw_end', False) else 0))

    db.commit()
    db.close()
    return graph_name


def main():
    parser = argparse.ArgumentParser(description='从 线路.csv 和 区间.csv 导入数据并写入 DB 或 JSON。')
    parser.add_argument('--line-csv', default=os.path.join(os.path.dirname(__file__), '线路.csv'), help='线路 CSV 文件路径')
    parser.add_argument('--section-csv', default=os.path.join(os.path.dirname(__file__), '区间.csv'), help='区间 CSV 文件路径')
    parser.add_argument('--output-json', default=None, help='输出 JSON 文件路径（可选，默认写入 DB）')
    parser.add_argument('--db', default=os.path.join(os.path.dirname(__file__), '..', 'data', 'running_train.db'), help='输出 DB 路径')
    args = parser.parse_args()

    line_rows, line_headers, line_enc = load_csv_rows(args.line_csv)
    section_rows, section_headers, section_enc = load_csv_rows(args.section_csv)
    print(f'Loaded line CSV ({line_enc}): {len(line_rows)} rows')
    print(f'Loaded section CSV ({section_enc}): {len(section_rows)} rows')

    graph_payload = build_train_graph(line_rows, section_rows, line_headers, section_headers, '上海周边')

    if args.output_json:
        # Export to JSON
        existing_graph = load_existing_graph(args.output_json)
        output_graph = write_graph_json(args.output_json, graph_payload, preserve_metadata=existing_graph)
        print(f'Wrote JSON to {args.output_json}')
        print(f'Generated {len(output_graph["TrainGraph"]["paths"])} paths')
    else:
        # Default: write to DB
        existing_graph = {}
        if os.path.exists(args.db):
            db = sqlite3.connect(args.db)
            existing = db.execute(
                'SELECT name, length, width, scale FROM train_graph WHERE name=?',
                ('上海周边',)).fetchone()
            if existing:
                existing_graph = {
                    'name': existing[0], 'length': existing[1],
                    'width': existing[2], 'scale': existing[3]}
            db.close()
        graph_name = write_graph_db(args.db, graph_payload, preserve_metadata=existing_graph)
        print(f'Wrote to DB {args.db}: graph="{graph_name}", {len(graph_payload["paths"])} paths')


if __name__ == '__main__':
    main()
