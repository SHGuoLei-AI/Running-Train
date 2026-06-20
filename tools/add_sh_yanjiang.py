import sqlite3
db = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

# Route 8: 上海→京沪→黄渡→沪苏通→太仓→沿江→南京南 (334km)
db.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('沪宁沿江(上海站)','上海','南京南',334,2)")
r8 = db.execute('SELECT last_insert_rowid()').fetchone()[0]
r8_stops = [
    ('上海','京沪线',0,0), ('上海西','京沪线',5,0), ('黄渡','京沪线',21,0),
    ('黄渡','沪苏通线',21,1), ('安亭西','沪苏通线',29,0),
    ('太仓南','沪苏通线',44,0), ('陆渡所','沪苏通线',54,0),
    ('太仓','沪苏通线',60,0),
    ('太仓','沪宁沿江高速线',60,1), ('常熟','沪宁沿江高速线',108,0),
    ('张家港','沪宁沿江高速线',125,0), ('江阴','沪宁沿江高速线',170,0),
    ('武进','沪宁沿江高速线',210,0), ('金坛','沪宁沿江高速线',249,0),
    ('句容','沪宁沿江高速线',294,0), ('高新园所','沪宁沿江高速线',319,0),
    ('南京南','沪宁沿江高速线',334,0),
]
for i,(st,ln,dist,is_j) in enumerate(r8_stops):
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',
               (r8,i+1,st,ln,dist,is_j))

# Route 9: 上海→京沪→黄渡→沪苏通→太仓→沿江→江宁联络→宁杭→南京南 (333km)
db.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('沪宁沿江江宁(上海站)','上海','南京南',333,4)")
r9 = db.execute('SELECT last_insert_rowid()').fetchone()[0]
r9_stops = [
    ('上海','京沪线',0,0), ('上海西','京沪线',5,0), ('黄渡','京沪线',21,0),
    ('黄渡','沪苏通线',21,1), ('安亭西','沪苏通线',29,0),
    ('太仓南','沪苏通线',44,0), ('陆渡所','沪苏通线',54,0),
    ('太仓','沪苏通线',60,0),
    ('太仓','沪宁沿江高速线',60,1), ('常熟','沪宁沿江高速线',108,0),
    ('张家港','沪宁沿江高速线',125,0), ('江阴','沪宁沿江高速线',170,0),
    ('武进','沪宁沿江高速线',210,0), ('金坛','沪宁沿江高速线',249,0),
    ('句容','沪宁沿江高速线',294,0), ('高新园所','沪宁沿江高速线',319,0),
    ('高新园所','江宁联络线',319,1), ('江宁','江宁联络线',322,0),
    ('江宁','宁杭高速线',322,1), ('南京南','宁杭高速线',333,0),
]
for i,(st,ln,dist,is_j) in enumerate(r9_stops):
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',
               (r9,i+1,st,ln,dist,is_j))

db.commit()
for r in db.execute('SELECT id,name,total_distance,junction_count FROM routes WHERE id>=8 ORDER BY id').fetchall():
    c = db.execute('SELECT COUNT(*) FROM route_stations WHERE route_id=?',(r[0],)).fetchone()[0]
    print(f'  Route {r[0]}: {r[1]}, {r[2]:.0f}km, {r[3]}接续, {c}站')
db.close()
