"""爬取 jprailfan.com 线路详情，写入 SQLite 数据库 data/kl.db

用法:
    python tools/huanghe-kl.py                # 批量爬取全部线路（支持断点续传）
    python tools/huanghe-kl.py --fresh        # 强制全新开始
    python tools/huanghe-kl.py 京沪线         # 查询指定线路详情
"""

import os
import sys
import re
import ssl
import time
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

BASE_URL = "https://jprailfan.com/tools/stat/"
MAIN_URL = BASE_URL + "?key7=" + urllib.parse.quote("所有线路输出到本页")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "kl.db")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REPORT_INTERVAL = 20


def get_db():
    return sqlite3.connect(DB_PATH)


def backup_db():
    """如果 kl.db 存在，重命名为带时间戳的备份。"""
    if not os.path.exists(DB_PATH):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        os.path.dirname(DB_PATH), f"huanghe_{timestamp}.db"
    )
    os.rename(DB_PATH, backup_path)
    print(f"已备份: {os.path.basename(backup_path)}")


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS line_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_name TEXT NOT NULL UNIQUE,
            start_station TEXT,
            end_station TEXT,
            mileage TEXT,
            remark TEXT
        );
        CREATE TABLE IF NOT EXISTS line_stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_name TEXT NOT NULL,
            station_name TEXT NOT NULL,
            pinyin_code TEXT,
            telegraph_code TEXT,
            station_no TEXT,
            railway_bureau TEXT,
            admin_region TEXT,
            dist_from_start TEXT,
            dist_from_prev TEXT,
            is_junction TEXT,
            junction_lines TEXT,
            restrictions TEXT,
            FOREIGN KEY (line_name) REFERENCES line_list(line_name)
        );
        CREATE TABLE IF NOT EXISTS scrape_log (
            line_name TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            station_count INTEGER,
            error_msg TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    db.close()


def get_completed():
    db = get_db()
    cur = db.execute("SELECT line_name FROM scrape_log")
    result = {row[0] for row in cur.fetchall()}
    db.close()
    return result


def log_attempt(line_name, status, station_count=0, error_msg=None):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO scrape_log (line_name, status, station_count, error_msg) "
        "VALUES (?, ?, ?, ?)",
        (line_name, status, station_count, error_msg),
    )
    db.commit()
    db.close()


def fetch_url(url: str, max_retries: int = 3) -> str:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 2
                print(f"  请求失败 ({e.__class__.__name__})，{wait}s 后重试...")
                time.sleep(wait)
    raise last_err


def fetch_line_list():
    """从主页面获取线路列表，返回 [(line_name, href), ...]."""
    print("正在获取线路列表...")
    html = fetch_url(MAIN_URL)

    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)
    if len(tables) < 2:
        raise ValueError("未找到线路列表表格")

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[1], re.DOTALL | re.IGNORECASE)

    lines = []
    for row in rows[1:]:  # 跳过表头
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        if not cells:
            continue

        # 从第一个 cell 提取线路名称和链接
        link_match = re.search(r"href=\"?([^\"\s>]+)\"?", cells[0])
        name = re.sub(r"<[^>]+>", "", cells[0]).strip()
        href = link_match.group(1) if link_match else None

        start_st = re.sub(r"<[^>]+>", "", cells[1]).strip() if len(cells) > 1 else ""
        end_st = re.sub(r"<[^>]+>", "", cells[2]).strip() if len(cells) > 2 else ""
        mileage = re.sub(r"<[^>]+>", "", cells[3]).strip() if len(cells) > 3 else ""
        remark = re.sub(r"<[^>]+>", "", cells[4]).strip() if len(cells) > 4 else ""

        lines.append((name, href, start_st, end_st, mileage, remark))

    print(f"  共 {len(lines)} 条线路\n")
    return lines


def parse_detail(html: str):
    """解析线路详情页，返回车站数据列表。"""
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)

    # 找到包含 途经车站 的表格（只有车站明细表有这个列名）
    target = None
    for t in tables:
        if "途经车站" in t:
            target = t
            break

    if not target:
        raise ValueError("未找到车站明细表")

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", target, re.DOTALL | re.IGNORECASE)

    def _extract(row_html):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.DOTALL)
        return [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

    all_rows = [_extract(r) for r in rows]

    # 跳过标题行和表头行 ("线路名称  途经车站  ...")
    header_start = 0
    for i, row in enumerate(all_rows):
        if row and row[0] == "线路名称":
            header_start = i
            break

    header = all_rows[header_start]
    data = all_rows[header_start + 1:]

    return header, data


def save_line_info(line_name, start_st, end_st, mileage, remark):
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO line_list
           (line_name, start_station, end_station, mileage, remark)
           VALUES (?, ?, ?, ?, ?)""",
        (line_name, start_st, end_st, mileage, remark),
    )
    db.commit()
    db.close()


def save_stations(line_name, header, data):
    db = get_db()
    for row in data:
        record = dict(zip(header, row))
        db.execute(
            """INSERT INTO line_stations
               (line_name, station_name, pinyin_code, telegraph_code, station_no,
                railway_bureau, admin_region, dist_from_start, dist_from_prev,
                is_junction, junction_lines, restrictions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                line_name,
                record.get("途经车站", ""),
                record.get("拼音码", ""),
                record.get("电报码", ""),
                record.get("车站编号", ""),
                record.get("所在路局", ""),
                record.get("所属行政区", ""),
                record.get("距起始站里程", ""),
                record.get("相邻站里程", ""),
                record.get("是否接算站", ""),
                record.get("该站接算线路", ""),
                record.get("办理限制", ""),
            ),
        )
    db.commit()
    db.close()


def scrape_one(line_name, href, start_st, end_st, mileage, remark, quiet=False):
    """爬取单条线路详情，返回车站列表长度或 None。"""
    try:
        url = BASE_URL + "?linename=" + urllib.parse.quote(line_name)
        html = fetch_url(url)
        header, data = parse_detail(html)
        save_line_info(line_name, start_st, end_st, mileage, remark)
        save_stations(line_name, header, data)
        log_attempt(line_name, "found", len(data))
        return len(data)
    except urllib.error.HTTPError as e:
        log_attempt(line_name, "skipped", error_msg=f"HTTP {e.code}")
        if not quiet:
            print(f"  {line_name}: HTTP {e.code}")
        return None
    except Exception as e:
        msg = str(e)[:200]
        log_attempt(line_name, "skipped", error_msg=msg)
        if not quiet:
            print(f"  {line_name}: {msg[:80]}")
        return None


def fmt_eta(seconds):
    if seconds <= 0:
        return "计算中"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def scrape_batch(fresh=False):
    if fresh:
        backup_db()
        init_db()
        completed = set()
        print("强制全新开始\n")
    elif os.path.exists(DB_PATH):
        init_db()
        completed = get_completed()
        if completed:
            print(f"检测到已有进度，{len(completed)} 条线路已完成，续传中...\n")
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

    lines = fetch_line_list()
    total = len(lines)
    remaining = total - len([l for l in lines if l[0] in completed])

    db = get_db()
    found_count = db.execute(
        "SELECT COUNT(*) FROM scrape_log WHERE status='found'"
    ).fetchone()[0]
    skipped_count = db.execute(
        "SELECT COUNT(*) FROM scrape_log WHERE status='skipped'"
    ).fetchone()[0]
    db.close()

    print(f"总线路: {total}  已完成: {len(completed)}  剩余: {remaining}")
    print(f"已找到: {found_count}  已跳过: {skipped_count}\n")

    start_time = time.time()
    recent_times = []

    found = 0
    skipped = 0
    processed = 0

    for line_name, href, start_st, end_st, mileage, remark in lines:
        if line_name in completed:
            continue

        t0 = time.time()
        result = scrape_one(line_name, href, start_st, end_st, mileage, remark)
        elapsed = time.time() - t0

        recent_times.append(elapsed)
        if len(recent_times) > 30:
            recent_times.pop(0)

        processed += 1
        if result:
            found += 1
            found_count += 1
            print(f"  [{found_count}] {line_name}  {result} 站")
        else:
            skipped += 1
            skipped_count += 1

        if processed % REPORT_INTERVAL == 0:
            done = len(completed) + found + skipped
            pct = done * 100 / total
            avg_time = sum(recent_times) / len(recent_times) if recent_times else 2
            eta = fmt_eta((total - done) * avg_time)
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"  [{now_str}] {done}/{total} ({pct:.1f}%)  "
                  f"已找到 {found_count}  预计剩余 {eta}")

    # 重试失败的线路（最多 5 次）
    retry_round = 0
    max_retries = 5

    while retry_round < max_retries:
        db = get_db()
        failed_lines = db.execute(
            "SELECT line_name FROM scrape_log WHERE status='skipped'"
        ).fetchall()
        db.close()

        if not failed_lines:
            break

        retry_round += 1
        failed_names = {row[0] for row in failed_lines}
        failed_list = [(n, h, ss, es, mi, rm)
                       for n, h, ss, es, mi, rm in lines if n in failed_names]

        print(f"\n第 {retry_round}/{max_retries} 次重试，{len(failed_list)} 条线路...\n")

        retry_found = 0
        for line_name, href, start_st, end_st, mileage, remark in failed_list:
            result = scrape_one(line_name, href, start_st, end_st, mileage, remark, quiet=True)
            if result:
                retry_found += 1
                found_count += 1
                skipped_count -= 1
                print(f"  [{found_count}] {line_name}  {result} 站 (重试{retry_round})")
            time.sleep(0.3)

        print(f"\n  重试{retry_round} 成功 {retry_found}，仍失败 {len(failed_list) - retry_found}")

    elapsed_total = time.time() - start_time
    print(f"\n完成！共找到 {found_count} 条线路，跳过 {skipped_count} 条。")
    print(f"本次耗时: {fmt_eta(elapsed_total)}")


def query_one(line_name):
    """查询并打印指定线路的车站明细。"""
    encoded = urllib.parse.quote(line_name)
    url = f"{BASE_URL}?linename={encoded}"
    print(f"正在查询 {line_name} ...\n")
    html = fetch_url(url)
    header, data = parse_detail(html)

    col_widths = [10, 6, 6, 8, 8, 8, 10, 10, 8, 20, 16]
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths[:len(header)])

    print(fmt.format(*header))
    print("-" * (sum(col_widths[:len(header)]) + (len(header) - 1) * 2))

    for row in data:
        print(fmt.format(*row))

    print(f"\n共 {len(data)} 站")


def main():
    if len(sys.argv) == 1:
        print("批量爬取全部线路（支持断点续传）...\n")
        scrape_batch()
        return

    arg = sys.argv[1]
    if arg == "--fresh":
        print("批量爬取（强制全新）...\n")
        scrape_batch(fresh=True)
    elif arg.startswith("-"):
        print(f"未知参数: {arg}")
        print("用法: python tools/huanghe-kl.py [线路名|--fresh]")
    else:
        query_one(arg)


if __name__ == "__main__":
    main()
