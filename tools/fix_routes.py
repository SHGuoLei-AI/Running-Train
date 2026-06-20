import sqlite3
db = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

# Route 4:沿江直达 - fix cum_distance
y4 = {'太仓':59,'岳东村所':64,'常熟':107,'张家港':124,'江阴':169,'武进':209,'金坛':248,'句容':293,'高新园所':318,'南京南':334}
for st,d in y4.items():
    db.execute('UPDATE route_stations SET cum_distance=? WHERE route_id=4 AND station_name=?',(d,st))
a4 = {'上海虹桥':0,'封浜':14,'黄渡':28,'安亭西':63,'太仓南':78,'陆渡所':88}
for st,d in a4.items():
    db.execute('UPDATE route_stations SET cum_distance=? WHERE route_id=4 AND station_name=?',(d,st))

# Route 5:沿江江宁联络 - fix cum_distance
a5 = {'上海虹桥':0,'封浜':14,'黄渡':28,'安亭西':63,'太仓南':78,'陆渡所':88,'太仓':59}
for st,d in a5.items():
    db.execute('UPDATE route_stations SET cum_distance=? WHERE route_id=5 AND station_name=?',(d,st))
y5 = {'太仓':59,'岳东村所':64,'常熟':107,'张家港':124,'江阴':169,'武进':209,'金坛':248,'句容':293,'高新园所':318}
for st,d in y5.items():
    db.execute('UPDATE route_stations SET cum_distance=? WHERE route_id=5 AND station_name=?',(d,st))
db.execute('UPDATE route_stations SET cum_distance=321 WHERE route_id=5 AND station_name="江宁"')
db.execute('UPDATE route_stations SET cum_distance=333 WHERE route_id=5 AND station_name="南京南"')

# Route 6:京沪高速上海站 - expand stations
db.execute('DELETE FROM route_stations WHERE route_id=6')
stops6 = [('上海','京沪高速线',0),('上海虹桥','京沪高速线',7),('黄渡所','京沪高速线',22),
          ('昆山南','京沪高速线',57),('苏州北','京沪高速线',88),('无锡东','京沪高速线',115),
          ('常州北','京沪高速线',172),('丹阳北','京沪高速线',205),('镇江南','京沪高速线',237),
          ('南京南','京沪高速线',302)]
for i,(st,ln,dist) in enumerate(stops6):
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance) VALUES (?,?,?,?,?)',(6,i+1,st,ln,dist))

db.commit()
for r in db.execute('SELECT id,name,total_distance FROM routes WHERE id IN (4,5,6)').fetchall():
    last = db.execute('SELECT cum_distance FROM route_stations WHERE route_id=? ORDER BY seq DESC LIMIT 1',(r[0],)).fetchone()[0]
    cnt = db.execute('SELECT COUNT(*) FROM route_stations WHERE route_id=?',(r[0],)).fetchone()[0]
    print(f'Route {r[0]}: {r[1]}, target={r[2]:.0f}km, last={last:.0f}km, {cnt} stations')
db.close()
