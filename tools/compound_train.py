"""复车次判断工具：识别互为复车次的车次对，更新 cc.db 的 full_train_no

规则:
  - 奇数车次 N 与 N+3 比较
  - 偶数车次 N 与 N+1 比较
  - 若停站、到发时间、停留时间完全一致，则为复车次
  - 更新 train_list.full_train_no 为 "N/M" 格式

用法:
    python tools/compound_train.py
"""

import os
import re
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cc.db")


def backup_db():
    if not os.path.exists(DB_PATH):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        os.path.dirname(DB_PATH), f"cc_{timestamp}.db"
    )
    # copy instead of rename
    import shutil
    shutil.copy2(DB_PATH, backup_path)
    print(f"已备份: {os.path.basename(backup_path)}")


def parse_train_no(train_no: str):
    """解析车次，返回 (字母前缀, 数字部分)。"""
    m = re.match(r"^([A-Z]*)(\d+)$", train_no)
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def get_stops(db, train_no):
    """获取车次的所有停站，返回 [(站名, 进站时间, 发车时间, 停留时间), ...]."""
    rows = db.execute(
        """SELECT station_name, arrival_time, departure_time, dwell_time
           FROM train_stops WHERE train_no = ?
           ORDER BY stop_seq""",
        (train_no,),
    ).fetchall()
    return rows


def stops_equal(stops_a, stops_b):
    """比较两个停站列表是否完全一致。"""
    if len(stops_a) != len(stops_b):
        return False
    for sa, sb in zip(stops_a, stops_b):
        if sa != sb:
            return False
    return True


def main():
    backup_db()

    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = OFF")

    trains = db.execute("SELECT train_no FROM train_list ORDER BY train_no").fetchall()
    train_set = {row[0] for row in trains}
    print(f"数据库中共 {len(train_set)} 个车次\n")

    # 先全部初始化为自身
    db.execute("UPDATE train_list SET full_train_no = train_no")
    db.commit()

    matched = 0
    for (train_no,) in trains:
        # 已经配对过的跳过
        cur = db.execute(
            "SELECT full_train_no FROM train_list WHERE train_no = ?", (train_no,)
        ).fetchone()
        if cur[0] != train_no:
            continue

        prefix, num = parse_train_no(train_no)
        if prefix is None:
            continue

        # 确定配对号
        if num % 2 == 1:  # 奇数 → +3
            pair_num = num + 3
        else:              # 偶数 → +1
            pair_num = num + 1

        pair_train = f"{prefix}{pair_num}"
        if pair_train not in train_set:
            continue

        # 如果对方已配过，跳过
        cur = db.execute(
            "SELECT full_train_no FROM train_list WHERE train_no = ?", (pair_train,)
        ).fetchone()
        if cur and cur[0] != pair_train:
            continue

        # 比较停站
        stops_a = get_stops(db, train_no)
        stops_b = get_stops(db, pair_train)
        if stops_equal(stops_a, stops_b):
            full = f"{train_no}/{pair_train}"
            db.execute(
                "UPDATE train_list SET full_train_no = ? WHERE train_no IN (?, ?)",
                (full, train_no, pair_train),
            )
            db.commit()
            matched += 1
            print(f"  [{matched}] {full}")

    db.commit()

    # 统计
    compound = db.execute(
        "SELECT COUNT(*) FROM train_list WHERE full_train_no != train_no"
    ).fetchone()[0]
    single = len(train_set) - compound

    db.close()
    print(f"\n完成！复车次: {compound // 2} 对 ({compound} 个车次)，单车次: {single} 个")


if __name__ == "__main__":
    main()
