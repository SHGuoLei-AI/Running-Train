import sqlite3
db = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

approach = [('上海虹桥','虹封线',0),('封浜','虹封线',14),
            ('封浜','黄南线',21,1),('黄渡','黄南线',28),
            ('黄渡','沪苏通线',28,1),('安亭西','沪苏通线',63),
            ('太仓南','沪苏通线',78),('陆渡所','沪苏通线',88),
            ('太仓','沪苏通线',94),
            ('太仓','沪宁沿江高速线',94,1),('岳东村所','沪宁沿江高速线',99),
            ('常熟','沪宁沿江高速线',142),('张家港','沪宁沿江高速线',159),
            ('江阴','沪宁沿江高速线',204),('武进','沪宁沿江高速线',244),
            ('金坛','沪宁沿江高速线',283)]

r4_tail = [('句容','沪宁沿江高速线',328),('高新园所','沪宁沿江高速线',353),('南京南','沪宁沿江高速线',369)]
db.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('沪宁沿江直达','上海虹桥','南京南',369,3)")
r4 = db.execute('SELECT last_insert_rowid()').fetchone()[0]
seq = 1
for row in approach:
    st,ln,dist = row[0],row[1],row[2]; is_j = row[3] if len(row)>3 else 0
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',(r4,seq,st,ln,dist,is_j)); seq += 1
for row in r4_tail:
    st,ln,dist = row[0],row[1],row[2]; is_j = row[3] if len(row)>3 else 0
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',(r4,seq,st,ln,dist,is_j)); seq += 1

r5_tail = [('句容','沪宁沿江高速线',328),('高新园所','沪宁沿江高速线',353),
           ('高新园所','江宁联络线',353,1),('江宁','江宁联络线',356),
           ('江宁','宁杭高速线',356,1),('南京南','宁杭高速线',368)]
db.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('沪宁沿江(江宁联络)','上海虹桥','南京南',368,4)")
r5 = db.execute('SELECT last_insert_rowid()').fetchone()[0]
seq = 1
for row in approach:
    st,ln,dist = row[0],row[1],row[2]; is_j = row[3] if len(row)>3 else 0
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',(r5,seq,st,ln,dist,is_j)); seq += 1
for row in r5_tail:
    st,ln,dist = row[0],row[1],row[2]; is_j = row[3] if len(row)>3 else 0
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',(r5,seq,st,ln,dist,is_j)); seq += 1

db.commit()
for r in db.execute('SELECT id,name,total_distance,junction_count FROM routes ORDER BY id').fetchall():
    c = db.execute('SELECT COUNT(*) FROM route_stations WHERE route_id=?',(r[0],)).fetchone()[0]
    print(f'  Route {r[0]}: {r[1]}, {r[2]:.0f}km, {r[3]}接续, {c}站')
db.close()
