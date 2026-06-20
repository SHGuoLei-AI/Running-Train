"""Route finder: find paths between stations using kl.db topology."""
import sqlite3, heapq
from collections import defaultdict

class RouteFinder:
    # Junction blacklist: (line_a, line_b, station) — these lines must NOT connect here
    JUNCTION_BLACKLIST = {
        ('京沪高速线', '沪宁高速线', '昆山南'),
        ('京沪高速线', '沪宁高速线', '安亭北'),
        ('京沪高速线', '沪宁高速线', '花桥'),
        ('京沪线', '沪宁高速线', '苏州'),
        ('京沪线', '沪宁高速线', '无锡'),
        ('京沪线', '沪宁高速线', '常州'),
        ('京沪线', '沪宁高速线', '丹阳'),
        ('京沪线', '沪宁高速线', '镇江'),
    }

    def __init__(self, db_path="data/kl.db"):
        self.db = sqlite3.connect(db_path)
        self._build_line_stations()
        self._build_topology()

    def _build_line_stations(self):
        """Map line_name -> ordered list of (station, dist_from_start)."""
        rows = self.db.execute('''
            SELECT line_name, station_name, dist_from_start
            FROM line_stations ORDER BY line_name, dist_from_start
        ''').fetchall()
        self.line_stops = defaultdict(list)
        for line, st, dist in rows:
            self.line_stops[line].append((st, dist))

    def _build_topology(self):
        """Build adjacency graph and station-line registry."""
        self.adj = defaultdict(list)       # station -> [(next_st, line, dist_delta)]
        self.station_lines = defaultdict(set)  # station -> {lines}

        for line, stops in self.line_stops.items():
            for i, (st, dist) in enumerate(stops):
                self.station_lines[st].add(line)
                if i > 0:
                    prev_st, prev_dist = stops[i-1]
                    self.adj[st].append((prev_st, line, dist - prev_dist))
                if i < len(stops) - 1:
                    next_st, next_dist = stops[i+1]
                    self.adj[st].append((next_st, line, next_dist - dist))

    def find_routes(self, start_station, end_station, max_transfers=2, max_routes=15):
        """Dijkstra-like search for routes from start to end.

        Returns list of routes, each = [(station, line, cum_dist_km), ...].
        """
        if start_station not in self.station_lines:
            return []
        if end_station not in self.station_lines:
            return []

        results = []
        total_seen = 0

        for start_line in self.station_lines[start_station]:
            if total_seen > 10000:  # Global safety limit
                break
            # Each start line gets its own search to avoid cross-contamination
            heap = [(0, start_station, start_line,
                     [(start_station, start_line, 0)], frozenset([start_line]))]
            seen_states = set()
            seen_states.add((start_station, frozenset([start_line])))

            while heap and len(seen_states) < 5000:
                cum_dist, cur_st, cur_line, path, lines_used = heapq.heappop(heap)

                for next_st, edge_line, edge_dist in self.adj.get(cur_st, []):
                    if next_st == start_station:
                        continue

                    new_dist = cum_dist + edge_dist
                    new_path = path + [(next_st, edge_line, new_dist)]
                    new_lines = lines_used | {edge_line}

                    # Check junction blacklist
                    if edge_line != cur_line:
                        k1 = (cur_line, edge_line, cur_st)
                        k2 = (edge_line, cur_line, cur_st)
                        if k1 in self.JUNCTION_BLACKLIST or k2 in self.JUNCTION_BLACKLIST:
                            continue

                    if (next_st, new_lines) in seen_states:
                        continue
                    seen_states.add((next_st, new_lines))

                    if next_st == end_station:
                        results.append(new_path)
                        continue

                    if edge_line != cur_line and len(new_lines) > max_transfers + 1:
                        continue

                    heapq.heappush(heap, (new_dist, next_st, edge_line, new_path, new_lines))

        # Sort by transfers first, then distance. Dedup: keep minimum-transfer version
        # But don't dedup different station sequences — those are genuinely different routes
        results.sort(key=lambda p: (len(set(l for s,l,d in p)) - 1, p[-1][2]))
        seen_seqs = {}
        unique = []
        for r in results:
            key = tuple(s for s, l, d in r)
            transfers = len(set(l for s,l,d in r)) - 1
            if key not in seen_seqs or transfers < seen_seqs[key]:
                seen_seqs[key] = transfers
                # Remove old version if exists
                unique = [u for u in unique if tuple(s for s,l,d in u) != key]
                unique.append(r)
        # Re-sort final by transfers first, then distance
        unique.sort(key=lambda p: (len(set(l for s,l,d in p)) - 1, p[-1][2]))
        # Filter: remove routes with backtracking (same station twice)
        unique = [r for r in unique if len(set(s for s,l,d in r)) == len(r)]
        return unique[:max_routes]

    def get_station_lines(self, station):
        return self.station_lines.get(station, set())

    def close(self):
        self.db.close()


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    rf = RouteFinder("data/kl.db")
    print("Station lines for 上海虹桥:", rf.get_station_lines("上海虹桥"))
    print("Station lines for 南京南:", rf.get_station_lines("南京南"))
    print("\nRoutes from 上海虹桥 to 南京南:")
    routes = rf.find_routes("上海虹桥", "南京南")
    for i, r in enumerate(routes):
        dist = r[-1][2]
        transfers = len(set(l for s, l, d in r)) - 1
        lines_used = list(dict.fromkeys(l for s, l, d in r))
        sts = [s for s, l, d in r]
        disp = ' -> '.join(sts[:4]) + (' ... ' + sts[-1] if len(sts) > 5 else ' -> '.join(sts[4:]))
        print(f"  [{i}] {transfers}换 {dist:.0f}km: {disp}")
        print(f"       线路: {' -> '.join(lines_used)}")
    rf.close()
