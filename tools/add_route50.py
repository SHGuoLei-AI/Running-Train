import sqlite3
db = sqlite3.connect(r'D:\work\running_train\data\running_train.db')
db.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('合杭(杭州-芜湖)','杭州','芜湖',269,2)")
r = db.execute('SELECT last_insert_rowid()').fetchone()[0]
stops = [('杭州','杭州线',0,0),('艮山门','杭州线',6,0),('笕桥','杭州线',12,0),
         ('笕桥','沪昆线',12,1),('杭州东','沪昆线',14,0),
         ('杭州东','宁杭高速线',14,1),('杭州东所','宁杭高速线',23,0),
         ('德清','宁杭高速线',58,0),('湖州','宁杭高速线',83,0),
         ('湖州','合杭高速线',83,1),('安吉','合杭高速线',127,0),
         ('广德南','合杭高速线',147,0),('郎溪南','合杭高速线',174,0),
         ('宣城','合杭高速线',203,0),('湾沚南','合杭高速线',229,0),
         ('芜湖南','合杭高速线',251,0),('芜湖','合杭高速线',269,0)]
for i,(st,ln,d,j) in enumerate(stops):
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',(r,i+1,st,ln,d,j))
db.commit()
print(f'Route {r}: 269km, total={db.execute("SELECT COUNT(*) FROM routes").fetchone()[0]}')
db.close()
