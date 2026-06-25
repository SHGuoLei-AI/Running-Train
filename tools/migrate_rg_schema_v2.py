"""rg.db schema v2 migration: drop graph_name, code; add sort_order

- railway_path: remove graph_name, code columns; add sort_order INTEGER
- railway_track: no changes needed
- train_graph: no changes needed
"""
import sqlite3
import shutil
import os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, BASE)
import config
DB_PATH = config.get_rg_path()
BACKUP_DIR = os.path.join(BASE, 'data', 'backup')


def main():
    # Backup
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'rg_v2_pre_migrate_{ts}.db')
    print(f'Backing up rg.db to {backup_path}')
    shutil.copy2(DB_PATH, backup_path)

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('PRAGMA foreign_keys = OFF')
        conn.execute('BEGIN')

        # Check current schema
        cols = conn.execute('PRAGMA table_info(railway_path)').fetchall()
        col_names = [c[1] for c in cols]
        print(f'Current railway_path columns: {col_names}')

        has_graph_name = 'graph_name' in col_names
        has_code = 'code' in col_names
        has_sort_order = 'sort_order' in col_names

        if has_sort_order and not has_graph_name and not has_code:
            print('Schema already migrated. Nothing to do.')
            conn.rollback()
            return

        # Create new table with desired schema
        conn.execute('''
            CREATE TABLE railway_path_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kl_line_name TEXT,
                start_x INTEGER,
                start_y INTEGER,
                angle INTEGER DEFAULT 0,
                hidden INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0
            )
        ''')

        # Migrate data: sort_order initialized from id (preserves existing order)
        conn.execute('''
            INSERT INTO railway_path_v2 (id, name, kl_line_name, start_x, start_y, angle, hidden, sort_order)
            SELECT id, name, kl_line_name, start_x, start_y, angle, hidden, id
            FROM railway_path
            ORDER BY id
        ''')

        row_count = conn.execute('SELECT COUNT(*) FROM railway_path_v2').fetchone()[0]
        print(f'Migrated {row_count} rows to railway_path_v2')

        # Drop old table and rename
        conn.execute('DROP TABLE railway_path')
        conn.execute('ALTER TABLE railway_path_v2 RENAME TO railway_path')

        # Drop obsolete index
        conn.execute('DROP INDEX IF EXISTS idx_rp_graph')

        conn.execute('PRAGMA foreign_keys = ON')
        conn.commit()
        print('Migration completed successfully.')

        # Verify
        cols_new = conn.execute('PRAGMA table_info(railway_path)').fetchall()
        print(f'New railway_path columns: {[c[1] for c in cols_new]}')
        count = conn.execute('SELECT COUNT(*) FROM railway_path').fetchone()[0]
        print(f'Row count: {count}')
    except Exception:
        conn.rollback()
        print('Migration failed, rolled back.')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
