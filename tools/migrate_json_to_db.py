"""One-time migration: import JSON train graph data into running_train.db."""
import json, sqlite3, os, sys
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE, 'data', '上海周边.json')
DB_PATH = os.path.join(BASE, 'data', 'running_train.db')

# 1. Load JSON
with open(JSON_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)
g = data['TrainGraph']

print(f'JSON: name={g["name"]}, {len(g["paths"])} paths, scale={g.get("scale", 1)}')

# 2. Connect to DB
db = sqlite3.connect(DB_PATH)

# 3. Clear existing data
graph_name = g['name']
print(f'Deleting existing data...')

db.execute('DELETE FROM railway_track')
db.execute('DELETE FROM railway_path')
db.execute('DELETE FROM train_graph WHERE name=?', (graph_name,))

# 4. Insert train_graph
db.execute(
    'INSERT INTO train_graph (name, length, width, scale) VALUES (?,?,?,?)',
    (g['name'], g['length'], g['width'], g.get('scale', 1))
)

# 5. Insert paths and tracks
path_count = 0
track_count = 0

for sort_order, p_data in enumerate(g['paths']):
    path_count += 1
    cursor = db.execute(
        'INSERT INTO railway_path (name, kl_line_name, start_x, start_y, angle, hidden, sort_order) '
        'VALUES (?,?,?,?,?,?,?)',
        (p_data['name'], '',
         p_data.get('start_x', 0), p_data.get('start_y', 0),
         p_data.get('angle', 0.0), 1 if p_data.get('hidden', False) else 0, sort_order)
    )
    path_id = cursor.lastrowid

    for seq, t_data in enumerate(p_data['tracks']):
        track_count += 1
        db.execute(
            'INSERT INTO railway_track (path_id, seq, head_station, tail_station, length, deflection, draw_head, draw_tail) '
            'VALUES (?,?,?,?,?,?,?,?)',
            (path_id, seq,
             t_data.get('head_station', ''),
             t_data.get('tail_station', ''),
             t_data['length'],
             t_data.get('deflection', 0),
             1 if t_data.get('draw_start', True) else 0,
             1 if t_data.get('draw_end', False) else 0)
        )

db.commit()

# 6. Verify
pg_cnt = db.execute('SELECT COUNT(*) FROM railway_path WHERE graph_name=?', (graph_name,)).fetchone()[0]
tk_cnt = db.execute('SELECT COUNT(*) FROM railway_track WHERE path_id IN (SELECT id FROM railway_path WHERE graph_name=?)', (graph_name,)).fetchone()[0]
print(f'Inserted: {path_count} paths, {track_count} tracks')
print(f'Verified: {pg_cnt} paths, {tk_cnt} tracks in DB')
assert path_count == pg_cnt, f'Path count mismatch: {path_count} vs {pg_cnt}'
assert track_count == tk_cnt, f'Track count mismatch: {track_count} vs {tk_cnt}'
print('Migration complete!')

db.close()
