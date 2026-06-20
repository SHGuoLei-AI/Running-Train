"""统计图内/图外车次。
图内站 = railway_track 表中 head_station 或 tail_station 出现的站。
图内车次 = 至少有一站在图内的车次。
"""
import sqlite3
import os
import sys

BASE = os.path.dirname(os.path.dirname(__file__))
RT = os.path.join(BASE, 'data', 'running_train.db')
SCHEDULE = os.path.join(BASE, 'data', 'llt_schedule.db')


def get_graph_stations(rt_conn):
    """返回图内站集合。"""
    rows = rt_conn.execute(
        'SELECT head_station FROM railway_track '
        'UNION SELECT tail_station FROM railway_track'
    ).fetchall()
    return {r[0] for r in rows}


def count_graph_trains(rt_conn, db_conn):
    """返回 (图内车次列表, 图外车次列表)."""
    graph_stations = get_graph_stations(rt_conn)
    trains = db_conn.execute(
        'SELECT train_index, train_name FROM trains'
    ).fetchall()

    in_graph = []
    out_graph = []

    for ti, name in trains:
        stops = db_conn.execute(
            'SELECT station_name FROM train_stops WHERE train_index=? ORDER BY stop_seq',
            (ti,)
        ).fetchall()
        if any(s[0] in graph_stations for s in stops):
            in_graph.append((ti, name))
        else:
            out_graph.append((ti, name))

    return in_graph, out_graph


def count_graph_stops(db_conn, train_index):
    """返回某车次在图内的停站数。"""
    graph_stations = get_graph_stations(db_conn)
    stops = db_conn.execute(
        'SELECT station_name FROM train_stops WHERE train_index=? ORDER BY stop_seq',
        (train_index,)
    ).fetchall()
    # Note: this opens a second connection; caller should pass graph_stations for efficiency
    return sum(1 for s in stops if s[0] in graph_stations)


def main():
    rt = sqlite3.connect(RT)
    db = sqlite3.connect(SCHEDULE)

    graph_stations = get_graph_stations(rt)
    in_graph, out_graph = count_graph_trains(rt, db)

    print(f'图内站: {len(graph_stations)} 个')
    print(f'图内车次: {len(in_graph)}')
    print(f'图外车次: {len(out_graph)}')
    print(f'车次总计: {len(in_graph) + len(out_graph)}')

    # 图内停站数分布
    from collections import Counter
    dist = Counter()
    for ti, _ in in_graph:
        stops = db.execute(
            'SELECT station_name FROM train_stops WHERE train_index=? ORDER BY stop_seq',
            (ti,)
        ).fetchall()
        cnt = sum(1 for s in stops if s[0] in graph_stations)
        dist[cnt] += 1

    print('\n图内停站数分布:')
    for k in sorted(dist):
        print(f'  {k}个图内站: {dist[k]} 车次')

    rt.close()
    db.close()


if __name__ == '__main__':
    main()
