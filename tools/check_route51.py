"""Check Route 51 distance deviations against actual trains."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

rt = sqlite3.connect(r'D:\work\running_train\data\running_train.db')
db = sqlite3.connect(r'D:\work\running_train\data\llt_schedule.db')

r = rt.execute('SELECT id, name, start_station, end_station, total_distance FROM routes WHERE id=51').fetchone()
if not r:
    print('Route 51 not found!')
    exit()
print(f'Route 51: {r[1]} | {r[2]}→{r[3]} | total={r[4]}km')
print()

sts = rt.execute('SELECT seq, station_name, line_name, cum_distance, is_junction FROM route_stations WHERE route_id=51 ORDER BY seq').fetchall()
print('Route 51 station list:')
for s in sts:
    j = ' [JUNCTION]' if s[4] else ''
    print(f'  {s[0]:2d}. {s[1]:10s}  {s[2]:18s}  {int(s[3]):4d}km{j}')
print()

# Load route stations dict
routes = rt.execute('SELECT id,name,start_station,end_station,total_distance FROM routes').fetchall()
route_stations = {}
for rr in routes:
    rid = rr[0]
    st = rt.execute('SELECT station_name, cum_distance FROM route_stations WHERE route_id=? ORDER BY seq', (rid,)).fetchall()
    route_stations[rid] = st
    route_stations[-rid] = [(x[0], rr[4] - x[1]) for x in reversed(st)]

train_ids = [rr[0] for rr in rt.execute('SELECT train_index FROM region_trains ORDER BY train_index').fetchall()]

matches_51 = []
for ti in train_ids:
    stops = db.execute('SELECT stop_seq,station_name,distance_km FROM train_stops WHERE train_index=? ORDER BY stop_seq', (ti,)).fetchall()
    if not stops: continue
    name = db.execute('SELECT train_name FROM trains WHERE train_index=?', (ti,)).fetchone()
    if not name: continue
    name = name[0]

    r_dists = {s[0]: s[1] for s in route_stations.get(51, [])}

    for i, si in enumerate(stops):
        for j in range(i + 1, len(stops)):
            sd = stops[j][2] - si[2]
            if si[1] in r_dists and stops[j][1] in r_dists:
                r_d = r_dists[stops[j][1]] - r_dists[si[1]]
                if r_d > 0:
                    dev = sd - r_d
                    matches_51.append((name, si[1], stops[j][1], sd, r_d, dev))

matches_51.sort(key=lambda x: -abs(x[5]))

print(f'Matches on Route 51 ({len(matches_51)} segments found), sorted by |deviation|:')
print(f'{"Train":16s} {"From":10s} {"To":10s} {"Trainkm":>8s} {"Routekm":>8s} {"Dev":>7s}')
for m in matches_51[:80]:
    flag = ' ***' if abs(m[5]) > 3 else ''
    print(f'{m[0]:16s} {m[1]:10s} {m[2]:10s} {m[3]:8.0f} {m[4]:8.0f} {m[5]:+7.0f}{flag}')

deviations = [m[5] for m in matches_51]
if deviations:
    print(f'\nStats: n={len(deviations)} | min={min(deviations):.0f} | max={max(deviations):.0f} | mean={sum(deviations)/len(deviations):.1f}')
    print(f'  |dev|>3km: {sum(1 for d in deviations if abs(d)>3)}')
    print(f'  |dev|<=3km: {sum(1 for d in deviations if abs(d)<=3)}')

    # Show trains that match 虹桥→南通 specifically
    print('\n--- 虹桥→南通 segments ---')
    for m in matches_51:
        if m[1] == '上海虹桥' and m[2] == '南通':
            print(f'{m[0]:16s} train={m[3]:.0f} route={m[4]:.0f} dev={m[5]:+.0f}')

    print('\n--- 虹桥→启东 segments ---')
    for m in matches_51:
        if m[1] == '上海虹桥' and m[2] == '启东':
            print(f'{m[0]:16s} train={m[3]:.0f} route={m[4]:.0f} dev={m[5]:+.0f}')

    # Group by train distance (虹桥→南通)
    print('\n--- Group by 虹桥→南通 train distance ---')
    from collections import Counter
    dists = Counter()
    for m in matches_51:
        if m[1] == '上海虹桥' and m[2] == '南通':
            dists[int(m[3])] += 1
    for d, c in sorted(dists.items()):
        print(f'  train_km={d}: {c} trains')

rt.close()
db.close()
