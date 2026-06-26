"""项目配置 — 图选择与DB路径解析"""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPHS_CONFIG = os.path.join(BASE_DIR, 'data', 'graphs.json')
SETUP_CONFIG = os.path.join(BASE_DIR, 'data', 'setup.json')


# ── setup.json — 全局设置（与图无关）──────────────────────

def load_setup() -> dict:
    if os.path.exists(SETUP_CONFIG):
        with open(SETUP_CONFIG, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_setup(data: dict):
    with open(SETUP_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_auto_backup() -> bool:
    return load_setup().get('auto_backup', True)


def set_auto_backup(enabled: bool):
    data = load_setup()
    data['auto_backup'] = enabled
    save_setup(data)


# ── graphs.json — 图列表配置 ─────────────────────────────


def _resolve(path: str) -> str:
    """将相对于项目根的路径转为绝对路径"""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(BASE_DIR, path))


def load_graphs() -> dict:
    """返回完整的 graphs.json 内容。"""
    if os.path.exists(GRAPHS_CONFIG):
        with open(GRAPHS_CONFIG, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'graphs': [], 'active': None}


def save_graphs(data: dict):
    """保存 graphs.json。"""
    with open(GRAPHS_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_active_graph() -> dict:
    """返回当前激活图的信息（基础路径）。"""
    cfg = load_graphs()
    active_id = cfg.get('active')
    for g in cfg.get('graphs', []):
        if g['id'] == active_id:
            return g
    graphs = cfg.get('graphs', [])
    return graphs[0] if graphs else {}


def _read_graph_prop(graph_id: str, prop: str):
    """从图的 rg.db train_graph 表读取属性。"""
    rg_path = get_graph_rg_path(graph_id)
    if not rg_path or not os.path.exists(rg_path):
        return None
    try:
        conn = sqlite3.connect(rg_path)
        row = conn.execute(f'SELECT {prop} FROM train_graph LIMIT 1').fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def get_graph_name(graph_id: str = None) -> str:
    """图的显示名称（从 rg.db train_graph.name 读取）。"""
    if graph_id is None:
        graph_id = load_graphs().get('active', '')
    return _read_graph_prop(graph_id, 'name') or graph_id


def get_rg_path() -> str:
    """当前激活图的 rg.db 绝对路径。"""
    g = get_active_graph()
    return _resolve(g.get('rg_db', 'data/rg.db'))


def get_rt_path() -> str:
    """当前激活图的 rt.db 绝对路径。"""
    g = get_active_graph()
    return _resolve(g.get('rt_db', 'data/rt.db'))


def get_graph_rg_path(graph_id: str) -> str:
    """指定图的 rg.db 路径。"""
    cfg = load_graphs()
    for g in cfg.get('graphs', []):
        if g['id'] == graph_id:
            return _resolve(g['rg_db'])
    return ''


def get_graph_rt_path(graph_id: str) -> str:
    """指定图的 rt.db 路径。"""
    cfg = load_graphs()
    for g in cfg.get('graphs', []):
        if g['id'] == graph_id:
            return _resolve(g['rt_db'])
    return ''


def set_active_graph(graph_id: str):
    """切换激活图。"""
    cfg = load_graphs()
    cfg['active'] = graph_id
    save_graphs(cfg)


def get_default_speed() -> float:
    """当前激活图的默认速度（从 rg.db train_graph 读取）。"""
    speed = _read_graph_prop(load_graphs().get('active', ''), 'default_speed')
    return float(speed) if speed is not None else 1.0


def get_recent_graphs(count: int = 3) -> list:
    """返回最近使用过的图 ID 列表。"""
    cfg = load_graphs()
    recent = cfg.get('recent', [])
    # 过滤掉已删除的图
    valid_ids = {g['id'] for g in cfg.get('graphs', [])}
    return [rid for rid in recent if rid in valid_ids][:count]


def record_recent_graph(graph_id: str):
    """记录图到最近使用列表。"""
    cfg = load_graphs()
    recent = cfg.get('recent', [])
    if graph_id in recent:
        recent.remove(graph_id)
    recent.insert(0, graph_id)
    cfg['recent'] = recent[:10]  # 保留最多 10 个
    save_graphs(cfg)


def add_graph(graph_id: str, rg_db: str, rt_db: str):
    """添加新图到配置（name/default_speed 在 rg.db 的 train_graph 表中）。"""
    cfg = load_graphs()
    cfg['graphs'].append({
        'id': graph_id,
        'rg_db': rg_db,
        'rt_db': rt_db,
    })
    cfg['active'] = graph_id
    record_recent_graph(graph_id)
    save_graphs(cfg)


def remove_graph(graph_id: str):
    """从配置中移除图。"""
    cfg = load_graphs()
    cfg['graphs'] = [g for g in cfg['graphs'] if g['id'] != graph_id]
    if cfg.get('active') == graph_id:
        cfg['active'] = cfg['graphs'][0]['id'] if cfg['graphs'] else None
    recent = cfg.get('recent', [])
    if graph_id in recent:
        recent.remove(graph_id)
    cfg['recent'] = recent
    save_graphs(cfg)
