# -*- coding: utf-8 -*-
import csv, sqlite3
from collections import defaultdict

with open('tools/train_route_match.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

rt = sqlite3.connect('data/running_train.db')
db = sqlite3.connect('data/llt_schedule.db')

all_route_stations = set()
for (s,) in rt.execute('SELECT DISTINCT station_name FROM route_stations').fetchall():
    all_route_stations.add(s)

no_match = [r for r in rows if 'R' not in r['经由匹配']]

single_hit = []
multi_hit = []

for r in no_match:
    name = r['车次']
    od = r['区段']
    ti = db.execute("SELECT train_index FROM trains WHERE train_name=?", (name,)).fetchone()
    if not ti: continue
    stops = db.execute("SELECT station_name, distance_km FROM train_stops WHERE train_index=? ORDER BY stop_seq", (ti[0],)).fetchall()
    hits = [(s[0], s[1]) for s in stops if s[0] in all_route_stations]
    stop_detail = [(s[0], s[1], s[0] in all_route_stations) for s in stops]
    if len(hits) == 1:
        single_hit.append((name, od, hits[0][0], stop_detail))
    elif len(hits) >= 2:
        multi_hit.append((name, od, len(hits), stop_detail, [h[0] for h in hits]))

by_station = defaultdict(list)
for name, od, hit_st, stops in single_hit:
    by_station[hit_st].append((name, od, stops))

lines = []
lines.append('# 零匹配车次排查详情')
lines.append('')
lines.append('> 共 273 趟零匹配车次，其中 1个路由站 254 趟，>=2个路由站 19 趟')
lines.append('')
lines.append('---')
lines.append('')

# Section 1: 上海 single-hit
shanghai_trains = by_station.pop('上海', [])
lines.append('## 一、上海单站（{} 趟）'.format(len(shanghai_trains)))
lines.append('')
lines.append('上海往徐州/北京等北方长途方向，只有上海站在路由网内，其余站全在网外。')
lines.append('')
lines.append('| 车次 | 区段 | 停站（路由站标*） |')
lines.append('|------|------|-------------------|')
for name, od, stops in shanghai_trains:
    st_str = '/'.join("{}{}".format(s[0], '*' if s[2] else '') for s in stops)
    lines.append('| {} | {} | {} |'.format(name, od, st_str))

lines.append('')
lines.append('---')
lines.append('')

# Section 2: other single-hit (NOT in top-7)
top7 = {'杭州西','杭州东','上海','南京南','芜湖','宁波','杭州'}
other_trains = []
for st, trains in sorted(by_station.items()):
    if st in top7:
        continue  # skip top-7, they go in summary only
    for name, od, stops in trains:
        other_trains.append((st, name, od, stops))
lines.append('## 二、其他单站（{} 趟）'.format(len(other_trains)))
lines.append('')
lines.append('除杭州西/杭州东/上海/南京南/芜湖/宁波/杭州以外的单路由站车次。')
lines.append('')
lines.append('| 路由站 | 车次 | 区段 | 停站（路由站标*） |')
lines.append('|--------|------|------|-------------------|')
for st, name, od, stops in sorted(other_trains, key=lambda x: (x[0], x[1])):
    st_str = '/'.join("{}{}".format(s[0], '*' if s[2] else '') for s in stops)
    lines.append('| {} | {} | {} | {} |'.format(st, name, od, st_str))

lines.append('')
lines.append('---')
lines.append('')

# Section 3: multi-hit
lines.append('## 三、>=2路由站但距离不匹配（{} 趟）'.format(len(multi_hit)))
lines.append('')
lines.append('有2个以上路由站，但站间距离与任何经由偏差>3km。')
lines.append('')

for name, od, nh, stops, hits in multi_hit:
    route_pairs = []
    for i in range(len(stops)):
        if stops[i][2]:
            for j in range(i+1, len(stops)):
                if stops[j][2]:
                    sd = stops[j][1] - stops[i][1]
                    route_pairs.append((stops[i][0], stops[j][0], sd))

    lines.append('### {} （{}）'.format(name, od))
    lines.append('')
    lines.append('路由站: {}'.format(", ".join(hits)))
    lines.append('')
    st_parts = []
    for s in stops:
        marker = '*' if s[2] else ''
        st_parts.append('{}{}({}km)'.format(s[0], marker, int(s[1])))
    lines.append('停站: {}'.format(" -> ".join(st_parts)))
    lines.append('')

    if route_pairs:
        lines.append('| 路由站对 | 车次距离 |')
        lines.append('|----------|----------|')
        for rs, re, sd in route_pairs:
            lines.append('| {} -> {} | {}km |'.format(rs, re, int(sd)))
        lines.append('')

lines.append('---')
lines.append('')

# Summary table
top7 = {'杭州西','杭州东','上海','南京南','芜湖','宁波','杭州'}
top7_labels = ['杭州西','杭州东','南京南','芜湖','宁波','杭州']
desc_map = {
    '杭州西': '杭州西->南昌/合肥/温州方向',
    '杭州东': '杭州东->苍南/南昌/厦门方向',
    '上海': '上海->北方长途',
    '南京南': '南京南->北京/徐州/西安方向',
    '芜湖': '芜湖->合肥/武汉方向',
    '宁波': '宁波->温州/厦门方向',
    '杭州': '杭州->金华/衢州方向',
}
summary_lines = []
summary_lines.append('## 汇总')
summary_lines.append('')
summary_lines.append('| 类别 | 数量 | 说明 |')
summary_lines.append('|------|------|------|')
summary_lines.append('| 上海单站 | {} | {} |'.format(len(shanghai_trains), desc_map['上海']))
summary_lines.append('| 其他单站 | {} | 路由站为端点但其他站不在网内 |'.format(len(other_trains)))
summary_lines.append('| 距离不匹配 | {} | >=2路由站但站间距离不在任何经由上 |'.format(len(multi_hit)))
for st in top7_labels:
    cnt = len(by_station.get(st, []))
    if cnt > 0:
        summary_lines.append('| {}单站 | {} | {} |'.format(st, cnt, desc_map.get(st, '')))
summary_lines.append('| **总计** | **{}** | |'.format(len(no_match)))

lines.extend(summary_lines)

with open('data/zero_match_detail.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('Written to data/zero_match_detail.md')
print('上海: {}, 其他: {}, 距离不匹配: {}'.format(len(shanghai_trains), len(other_trains), len(multi_hit)))
for st in top7_labels:
    print('  {}: {}'.format(st, len(by_station.get(st, []))))

db.close()
rt.close()
