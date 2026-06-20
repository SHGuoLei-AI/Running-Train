"""Fix Route 36 distances using kl data."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

rt = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

# Delete old route_stations
rt.execute('DELETE FROM route_stations WHERE route_id=36')

# kl data:
# 京沪线: 南京(1162) → 林场(1147) = 15km
# 宁启线(南京): 林场(0)→六合(35)→仪征(65)→扬州(86)→泰安镇(104)→江都(111)→
#              泰州(150)→姜堰(164)→海安(204)→如皋(224)→赵甸(255)→
#              平东所(258)→陈桥所(260)→南通(269)→海门(307)→启东(352)

NINGQI_BASE = 15  # 南京→林场 via 京沪线

stops = [
    # (station, line, cum_distance, is_junction)
    ('南京', '京沪线', 0, 0),
    ('林场', '京沪线', 15, 0),
    ('林场', '宁启线(南京)', 15, 1),
    ('六合', '宁启线(南京)', 50, 0),
    ('仪征', '宁启线(南京)', 80, 0),
    ('扬州', '宁启线(南京)', 101, 0),
    ('泰安镇', '宁启线(南京)', 119, 0),
    ('江都', '宁启线(南京)', 126, 0),
    ('泰州', '宁启线(南京)', 165, 0),
    ('姜堰', '宁启线(南京)', 179, 0),
    ('海安', '宁启线(南京)', 219, 0),
    ('如皋', '宁启线(南京)', 239, 0),
    ('赵甸', '宁启线(南京)', 270, 0),
    ('平东所', '宁启线(南京)', 273, 0),
    ('陈桥所', '宁启线(南京)', 275, 0),
    ('南通', '宁启线(南京)', 284, 0),
    ('海门', '宁启线(南京)', 322, 0),
    ('启东', '宁启线(南京)', 367, 0),
]

rt.execute('UPDATE routes SET total_distance=367, junction_count=1 WHERE id=36')

for i, (st, ln, d, j) in enumerate(stops):
    rt.execute(
        'INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',
        (36, i + 1, st, ln, d, j)
    )

rt.commit()

# Verify
r = rt.execute('SELECT id,name,start_station,end_station,total_distance FROM routes WHERE id=36').fetchone()
print(f'Route {r[0]}: {r[1]} | {r[2]}→{r[3]} | {r[4]}km')
sts = rt.execute('SELECT seq, station_name, line_name, cum_distance, is_junction FROM route_stations WHERE route_id=36 ORDER BY seq').fetchall()
for s in sts:
    j = ' [J]' if s[4] else ''
    print(f'  {s[0]:2d}. {s[1]:8s}  {s[2]:16s}  {int(s[3]):4d}km{j}')

print(f'\nKey: 南通→海安={284-219}=65km  泰州→江都={165-126}=39km  南京→南通=284km')
rt.close()
