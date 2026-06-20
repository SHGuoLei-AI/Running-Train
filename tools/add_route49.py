import sqlite3
db = sqlite3.connect(r'D:\work\running_train\data\running_train.db')
db.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('沪苏湖合杭上海南-杭州西','上海南','杭州西',219,2)")
r = db.execute('SELECT last_insert_rowid()').fetchone()[0]
stops = [('上海南','沪春线',0,0),('春申南所','沪春线',11,0),
         ('春申南所','沪苏湖高速线',11,1),('上海松江','沪苏湖高速线',28,0),
         ('练塘','沪苏湖高速线',47,0),('苏州南','沪苏湖高速线',71,0),
         ('盛泽','沪苏湖高速线',101,0),('湖州南浔','沪苏湖高速线',119,0),
         ('湖州东','沪苏湖高速线',141,0),('康山所','沪苏湖高速线',154,0),
         ('湖州','沪苏湖高速线',161,0),
         ('湖州','合杭高速线',161,1),('德清','合杭高速线',197,0),
         ('杭州西','合杭高速线',219,0)]
for i,(st,ln,d,j) in enumerate(stops):
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',(r,i+1,st,ln,d,j))
db.commit()
print(f'Route {r}: 219km, total={db.execute("SELECT COUNT(*) FROM routes").fetchone()[0]}')
db.close()
