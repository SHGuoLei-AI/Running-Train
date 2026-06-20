"""Add Route 55: 上海南→杭州南 via 沪春→金山→沪昆."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

rt = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

# 沪春线: 上海南(0)→莘庄(6)→春申南所(11)
# 金山线: 春申南所(0)→春申(1)
# 沪昆线: 春申(40)→新桥(45)→上海松江(56)→枫泾(82)→嘉善(92)→嘉兴(110)→
#         海宁(138)→笕桥(191)→杭州东(197)→杭州南(218)

rt.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('沪昆线(上海南-杭州南)','上海南','杭州南',190,3)")

r = rt.execute('SELECT last_insert_rowid()').fetchone()[0]

stops = [
    ('上海南', '沪春线', 0, 0),
    ('莘庄', '沪春线', 6, 0),
    ('春申南所', '沪春线', 11, 0),
    ('春申南所', '金山线', 11, 1),
    ('春申', '金山线', 12, 0),
    ('春申', '沪昆线', 12, 1),
    ('新桥', '沪昆线', 17, 0),
    ('上海松江', '沪昆线', 28, 0),
    ('枫泾', '沪昆线', 54, 0),
    ('嘉善', '沪昆线', 64, 0),
    ('嘉兴', '沪昆线', 82, 0),
    ('海宁', '沪昆线', 110, 0),
    ('笕桥', '沪昆线', 163, 0),
    ('杭州东', '沪昆线', 169, 0),
    ('杭州南', '沪昆线', 190, 0),
]

for i, (st, ln, d, j) in enumerate(stops):
    rt.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',
               (r, i + 1, st, ln, d, j))

rt.commit()

print(f'Route {r}: 沪昆线(上海南-杭州南) 190km')
print('  Key: 上海南→杭州东=169km  上海南→上海松江=28km  杭州南→上海松江=162km')
print(f'  Total routes: {rt.execute("SELECT COUNT(*) FROM routes").fetchone()[0]}')
rt.close()
