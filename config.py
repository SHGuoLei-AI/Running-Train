"""项目配置 — 图选择与DB路径解析"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPHS_CONFIG = os.path.join(BASE_DIR, 'data', 'graphs.json')


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
    """返回当前激活图的信息。"""
    cfg = load_graphs()
    active_id = cfg.get('active')
    for g in cfg.get('graphs', []):
        if g['id'] == active_id:
            return g
    # fallback: return first graph
    graphs = cfg.get('graphs', [])
    return graphs[0] if graphs else {}


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
