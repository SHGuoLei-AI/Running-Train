"""爬取携程火车时刻表信息，写入 SQLite 数据库 data/cc.db

用法:
    python tools/ctrip-cc.py                    # 默认查询 G1784
    python tools/ctrip-cc.py G1784              # 查询指定车次
    python tools/ctrip-cc.py --batch            # 批量爬取（支持断点续传）
    python tools/ctrip-cc.py --batch --fresh    # 强制重新开始（备份旧库）
"""

import os
import sys
import re
import time
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime

BASE_URL = "https://trains.ctrip.com/TrainSchedule/{}"
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cc.db")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

LETTER_PREFIXES = ["G", "D", "C", "Z", "T", "K", "S", "Y"]
TOTAL_COUNT = 2 + 5000 + 8 * 10000  # 85002
EST_VALID = 12000
REPORT_INTERVAL = 100


def generate_train_numbers():
    """按规则生成全部待爬取车次（字母后数字不含前导零）。"""
    for tn in ["1461", "1462"]:
        yield tn
    for prefix in range(4, 9):
        for i in range(1000):
            yield f"{prefix}{i:03d}"
    for letter in LETTER_PREFIXES:
        for i in range(10000):
            yield f"{letter}{i}"


def backup_db():
    """如果 cc.db 存在，重命名为 cc_YYYYMMDD_HHMMSS.db。"""
    if not os.path.exists(DB_PATH):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        os.path.dirname(DB_PATH), f"cc_{timestamp}.db"
    )
    os.rename(DB_PATH, backup_path)
    print(f"已备份: {os.path.basename(backup_path)}")


def fetch_page(train_no: str) -> str:
    url = BASE_URL.format(train_no)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def parse_schedule(html: str):
    """从 HTML 中解析时刻表，返回列名和数据行列表。"""
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)
    if len(tables) < 2:
        raise ValueError("未找到时刻表，页面结构可能已变化")

    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[1], re.DOTALL | re.IGNORECASE)

    def _extract_cells(row_html):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.DOTALL)
        return [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

    all_rows = [_extract_cells(r) for r in rows_html]

    header = all_rows[0][1:-1]
    data = [row[1:-1] for row in all_rows[1:]]

    return header, data


def get_db():
    """获取数据库连接。"""
    return sqlite3.connect(DB_PATH)


def init_db():
    """初始化数据库表（含断点续传日志）。"""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS train_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_no TEXT NOT NULL UNIQUE,
            full_train_no TEXT,
            internal_no TEXT
        );
        CREATE TABLE IF NOT EXISTS train_stops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_no TEXT NOT NULL,
            stop_seq INTEGER NOT NULL,
            station_name TEXT NOT NULL,
            arrival_time TEXT,
            departure_time TEXT,
            dwell_time TEXT,
            FOREIGN KEY (train_no) REFERENCES train_list(train_no),
            UNIQUE(train_no, stop_seq)
        );
        CREATE TABLE IF NOT EXISTS scrape_log (
            train_no TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            stop_count INTEGER,
            error_msg TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    db.close()


def get_completed():
    """返回已爬取过的车次集合。"""
    db = get_db()
    cur = db.execute("SELECT train_no FROM scrape_log")
    result = {row[0] for row in cur.fetchall()}
    db.close()
    return result


def log_attempt(train_no, status, stop_count=0, error_msg=None):
    """记录每次爬取尝试。"""
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO scrape_log (train_no, status, stop_count, error_msg) VALUES (?, ?, ?, ?)",
        (train_no, status, stop_count, error_msg),
    )
    db.commit()
    db.close()


def save_to_db(train_no, header, data):
    """将时刻表写入数据库。"""
    db = get_db()
    db.execute("INSERT OR IGNORE INTO train_list (train_no) VALUES (?)", (train_no,))
    for row in data:
        record = dict(zip(header, row))
        db.execute(
            """INSERT OR REPLACE INTO train_stops
                (train_no, stop_seq, station_name, arrival_time, departure_time, dwell_time)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                train_no,
                int(record["停靠站序"]),
                record["站名"],
                record["进站时间"],
                record["发车时间"],
                record["停留时间"],
            ),
        )
    db.commit()
    db.close()


def scrape_one(train_no):
    """爬取单个车次，返回 (header, data) 或 None，并记录日志。"""
    try:
        html = fetch_page(train_no)
        header, data = parse_schedule(html)
        save_to_db(train_no, header, data)
        log_attempt(train_no, "found", len(data))
        return header, data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log_attempt(train_no, "skipped", error_msg="404")
            return None
        log_attempt(train_no, "skipped", error_msg=f"HTTP {e.code}")
        print(f"  {train_no}: HTTP {e.code}")
        return None
    except Exception as e:
        msg = str(e)
        log_attempt(train_no, "skipped", error_msg=msg[:200])
        print(f"  {train_no}: {msg[:80]}")
        return None


def fmt_eta(seconds):
    """格式化剩余时间。"""
    if seconds <= 0:
        return "计算中"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def scrape_batch(fresh=False):
    """批量爬取全部车次，支持断点续传。"""
    if fresh:
        backup_db()
        init_db()
        completed = set()
        print("全新开始\n")
    elif os.path.exists(DB_PATH):
        init_db()
        completed = get_completed()
        if completed:
            print(f"检测到已有进度，{len(completed)} 个车次已完成，续传中...\n")
        else:
            backup_db()
            init_db()
            completed = set()
            print("全新开始\n")
    else:
        backup_db()
        init_db()
        completed = set()
        print("全新开始\n")

    # 重新获取准确的已找到数量
    db = get_db()
    found_count = db.execute(
        "SELECT COUNT(*) FROM scrape_log WHERE status='found'"
    ).fetchone()[0]
    skipped_count = db.execute(
        "SELECT COUNT(*) FROM scrape_log WHERE status='skipped'"
    ).fetchone()[0]
    db.close()

    done_before = found_count + skipped_count
    remaining = TOTAL_COUNT - done_before

    print(f"总车次: {TOTAL_COUNT}  已完成: {done_before}  剩余: {remaining}")
    print(f"已找到: {found_count}  已跳过: {skipped_count}")
    print()

    # 时间估算
    start_time = time.time()
    recent_times = []  # 最近 50 次耗时

    found = 0
    skipped = 0
    processed = 0

    for train_no in generate_train_numbers():
        if train_no in completed:
            continue

        t0 = time.time()
        result = scrape_one(train_no)
        elapsed = time.time() - t0

        recent_times.append(elapsed)
        if len(recent_times) > 50:
            recent_times.pop(0)

        processed += 1
        if result:
            found += 1
            found_count += 1
            print(f"  [{found_count}] {train_no}  {len(result[1])} 站")
        else:
            skipped += 1
            skipped_count += 1

        if processed % REPORT_INTERVAL == 0:
            done = done_before + found + skipped
            pct = done * 100 / TOTAL_COUNT
            avg_time = sum(recent_times) / len(recent_times)
            remaining_estimated = (TOTAL_COUNT - done) * avg_time
            eta = fmt_eta(remaining_estimated)
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"  [{now_str}] {done}/{TOTAL_COUNT} ({pct:.1f}%)  "
                  f"已找到 {found_count}  预计剩余 {eta}")

    elapsed_total = time.time() - start_time
    print(f"\n完成！共找到 {found_count} 个车次，跳过 {skipped_count} 个。")
    print(f"本次耗时: {fmt_eta(elapsed_total)}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        fresh = len(sys.argv) > 2 and sys.argv[2] == "--fresh"
        if fresh:
            print("批量爬取（强制全新）...\n")
        else:
            print("批量爬取（支持断点续传）...\n")
        scrape_batch(fresh=fresh)
        return

    train_no = sys.argv[1] if len(sys.argv) > 1 else "G1784"
    print(f"正在查询 {train_no} 时刻表...\n")

    html = fetch_page(train_no)
    header, data = parse_schedule(html)

    col_widths = [6, 10, 10, 10, 10]
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)

    print(fmt.format(*header))
    print("-" * sum(col_widths) + "-" * (len(col_widths) * 2 - 1))

    for row in data:
        print(fmt.format(*row))

    print(f"\n共 {len(data)} 站")

    save_to_db(train_no, header, data)
    print(f"已写入数据库: {DB_PATH}")


if __name__ == "__main__":
    main()
