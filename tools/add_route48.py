import sqlite3
db = sqlite3.connect(r'D:\work\running_train\data\running_train.db')
db.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('连镇沪宁','扬州东','上海',286,1)")
r = db.execute('SELECT last_insert_rowid()').fetchone()[0]
stops = [('扬州东','连镇客专线',0,0),('大港南','连镇客专线',43,0),
         ('横山所','连镇客专线',57,0),('丹徒','连镇客专线',62,0),
         ('丹徒','沪宁高速线',62,1),('丹阳','沪宁高速线',76,0),
         ('常州','沪宁高速线',121,0),('无锡','沪宁高速线',160,0),
         ('苏州','沪宁高速线',202,0),('昆山南','沪宁高速线',236,0),
         ('上海西','沪宁高速线',281,0),('上海','沪宁高速线',286,0)]
for i,(st,ln,d,j) in enumerate(stops):
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',(r,i+1,st,ln,d,j))
db.commit()
print(f'Route 48: 286km, total={db.execute("SELECT COUNT(*) FROM routes").fetchone()[0]}')
db.close()
