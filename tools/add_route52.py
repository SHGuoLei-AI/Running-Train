import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

rt = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

# 杭甬线: 杭州(0)→杭州南(27)→绍兴(63)→上虞(91)→余姚(123)→庄桥(163)→宁波(171)
rt.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('杭甬线(杭州-宁波)','杭州','宁波',171,1)")

r = rt.execute('SELECT last_insert_rowid()').fetchone()[0]

stops = [
    ('杭州', '杭甬线', 0, 0),
    ('杭州南', '杭甬线', 27, 0),
    ('杭州南', '杭甬线', 27, 1),  # junction for 沪昆线 connection
    ('绍兴', '杭甬线', 63, 0),
    ('上虞', '杭甬线', 91, 0),
    ('余姚', '杭甬线', 123, 0),
    ('庄桥', '杭甬线', 163, 0),
    ('宁波', '杭甬线', 171, 0),
]

for i, (st, ln, d, j) in enumerate(stops):
    rt.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)', (r, i+1, st, ln, d, j))

rt.commit()
print(f'Route {r}: 杭甬线(杭州-宁波) 171km')
print(f'Total routes: {rt.execute("SELECT COUNT(*) FROM routes").fetchone()[0]}')
rt.close()
