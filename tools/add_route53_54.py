import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

rt = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

# Route 53: 扬州东→南京 = 133km
# 连镇客专: 扬州东(242)→横山所(299)=57km
# 镇江联络线: 横山所(0)→镇江(12)=12km
# 沪宁高速线: 镇江(237)→南京(301)=64km

rt.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('连镇沪宁(扬州东-南京)','扬州东','南京',133,2)")
r53 = rt.execute('SELECT last_insert_rowid()').fetchone()[0]

stops = [
    ('扬州东', '连镇客专线', 0, 0),
    ('大港南', '连镇客专线', 43, 0),
    ('横山所', '连镇客专线', 57, 0),
    ('横山所', '镇江联络线', 57, 1),
    ('镇江', '镇江联络线', 69, 0),
    ('镇江', '沪宁高速线', 69, 1),
    ('宝华山', '沪宁高速线', 106, 0),
    ('仙林', '沪宁高速线', 120, 0),
    ('南京', '沪宁高速线', 133, 0),
]

for i, (st, ln, d, j) in enumerate(stops):
    rt.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',
               (r53, i+1, st, ln, d, j))

print(f'Route {r53}: 连镇沪宁(扬州东-南京) 133km')

# Route 54: 扬州东→南京南 = 143km
# 连镇客专: 扬州东(242)→横山所(299)=57km
# 镇江联络线: 横山所(0)→镇江(12)=12km
# 沪宁高速线: 镇江(237)→仙林(288)=51km
# 仙宁线: 仙林(0)→南京南(23)=23km

rt.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('连镇沪宁仙宁(扬州东-南京南)','扬州东','南京南',143,3)")
r54 = rt.execute('SELECT last_insert_rowid()').fetchone()[0]

stops = [
    ('扬州东', '连镇客专线', 0, 0),
    ('大港南', '连镇客专线', 43, 0),
    ('横山所', '连镇客专线', 57, 0),
    ('横山所', '镇江联络线', 57, 1),
    ('镇江', '镇江联络线', 69, 0),
    ('镇江', '沪宁高速线', 69, 1),
    ('宝华山', '沪宁高速线', 106, 0),
    ('仙林', '沪宁高速线', 120, 0),
    ('仙林', '仙宁线', 120, 1),
    ('南京南', '仙宁线', 143, 0),
]

for i, (st, ln, d, j) in enumerate(stops):
    rt.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',
               (r54, i+1, st, ln, d, j))

print(f'Route {r54}: 连镇沪宁仙宁(扬州东-南京南) 143km')

rt.commit()
print(f'Total routes: {rt.execute("SELECT COUNT(*) FROM routes").fetchone()[0]}')
rt.close()
