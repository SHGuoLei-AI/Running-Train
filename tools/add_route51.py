import sqlite3
db = sqlite3.connect(r'D:\work\running_train\data\running_train.db')
# 虹桥→启东:虹封+黄南+沪苏通+宁启 ≈246km
db.execute("INSERT INTO routes (name,start_station,end_station,total_distance,junction_count) VALUES ('沪苏通宁启(虹桥-启东)','上海虹桥','启东',246,3)")
r = db.execute('SELECT last_insert_rowid()').fetchone()[0]
stops = [('上海虹桥','虹封线',0,0),('封浜','虹封线',14,0),
         ('封浜','黄南线',14,1),('黄渡','黄南线',21,0),
         ('黄渡','沪苏通线',21,1),('安亭西','沪苏通线',29,0),
         ('太仓','沪苏通线',58,0),('常熟','沪苏通线',106,0),
         ('张家港','沪苏通线',124,0),('南通西','沪苏通线',143,0),
         ('赵甸','沪苏通线',149,0),
         ('赵甸','宁启线(南京)',149,1),('南通','宁启线(南京)',163,0),
         ('海门','宁启线(南京)',201,0),('启东','宁启线(南京)',246,0)]
for i,(st,ln,d,j) in enumerate(stops):
    db.execute('INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',(r,i+1,st,ln,d,j))
db.commit()
print(f'Route {r}: 246km, total={db.execute("SELECT COUNT(*) FROM routes").fetchone()[0]}')
db.close()
