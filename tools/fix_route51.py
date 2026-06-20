"""Fix Route 51: use 赵甸联络线 instead of 赵甸 station."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

rt = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

# Delete old route_stations
rt.execute('DELETE FROM route_stations WHERE route_id=51')

# Route: 虹封→黄南→沪苏通→赵甸联络线→宁启
# kl distances:
#   虹封线: 虹桥(0)→封浜(14)
#   黄南线: 封浜→黄渡(7km)
#   沪苏通线: 黄渡(143 from赵甸)→南通西(6 from赵甸), dist=137km
#   赵甸联络线: 南通西(4 from平东所)→平东所(0), dist=4km  (南通西→平东所方向)
#   宁启线(南京): 平东所(258)→南通(269)=11, 海门(307)=49, 启东(352)=94

cum_nantongxi = 21 + 137  # = 158
cum_pingdong = cum_nantongxi + 4  # = 162
total = cum_pingdong + 94  # = 256

rt.execute('UPDATE routes SET total_distance=?, junction_count=?, name=? WHERE id=51',
           (total, 3, '沪苏通宁启(虹桥-启东)'))

stops = [
    # (station, line, cum_distance, is_junction)
    ('上海虹桥', '虹封线', 0, 0),
    ('封浜', '虹封线', 14, 0),
    ('封浜', '黄南线', 14, 1),
    ('黄渡', '黄南线', 21, 0),
    ('黄渡', '沪苏通线', 21, 1),
    ('安亭西', '沪苏通线', 29, 0),
    ('太仓南', '沪苏通线', 44, 0),
    ('陆渡所', '沪苏通线', 54, 0),
    ('太仓', '沪苏通线', 58, 0),
    ('常熟', '沪苏通线', 106, 0),
    ('张家港', '沪苏通线', 124, 0),
    ('南通西', '沪苏通线', 158, 0),
    ('南通西', '赵甸联络线', 158, 1),
    ('平东所', '赵甸联络线', 162, 0),
    ('平东所', '宁启线(南京)', 162, 1),
    ('南通', '宁启线(南京)', 173, 0),
    ('海门', '宁启线(南京)', 211, 0),
    ('启东', '宁启线(南京)', 256, 0),
]

for i, (st, ln, d, j) in enumerate(stops):
    rt.execute(
        'INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',
        (51, i + 1, st, ln, d, j)
    )

rt.commit()

# Verify
r = rt.execute('SELECT id,name,start_station,end_station,total_distance FROM routes WHERE id=51').fetchone()
print(f'Route 51: {r[1]} | {r[2]}→{r[3]} | total={r[4]}km')
sts = rt.execute('SELECT seq, station_name, line_name, cum_distance, is_junction FROM route_stations WHERE route_id=51 ORDER BY seq').fetchall()
for s in sts:
    j = ' [J]' if s[4] else ''
    print(f'  {s[0]:2d}. {s[1]:8s}  {s[2]:16s}  {int(s[3]):4d}km{j}')

print(f'\n虹桥→南通西: 158km')
print(f'虹桥→南通: 173km')
print(f'虹桥→启东: 256km')

rt.close()
