# Running Train

基于 PySide6 的铁路运行动态模拟工具，支持多图切换。

> 最新状态与更新记录见 [UPDATES.md](UPDATES.md)

## 数据架构

```
data/
├── kl.db             # 客里表 (536 KB) — 756 线, 6654 站（共用）
├── cc.db             # 时刻表 (12 MB) — 3298 站, 17168 车次（共用）
├── rg-xinjiang.db    # 几何结构 — 新疆区域
├── rt-xinjiang.db    # 图上车次 — 新疆区域
├── rg-shanghai.db    # 几何结构 — 上海区域
├── rt-shanghai.db    # 图上车次 — 上海区域
├── rg-chuanyu.db     # 几何结构 — 川渝区域
├── rt-chuanyu.db     # 图上车次 — 川渝区域
├── rg-shangannin.db  # 几何结构 — 陕甘宁-蒙西区域
├── rt-shangannin.db  # 图上车次 — 陕甘宁-蒙西区域
├── kl_revisions.md   # 客里表修订记录
├── graphs.json       # 图配置文件（仅 id + 路径）
├── setup.json        # 全局设置（auto_backup 等）
├── backup/           # 自动备份 (不入 git)
├── old/              # 旧文件归档 (不入 git)
└── 数据结构.md        # 完整 schema 文档
```

> 图名称和默认速度存在各 `rg-{id}.db` 的 `train_graph` 表中。

### 多图切换

通过 `data/graphs.json` 管理多个运行图。菜单 **图(&G)** 可在不同图之间切换：

```
graphs.json:
{
    "graphs": [
        {"id": "xinjiang", "rg_db": "data/rg-xinjiang.db", "rt_db": "data/rt-xinjiang.db"},
        {"id": "shanghai", "rg_db": "data/rg-shanghai.db", "rt_db": "data/rt-shanghai.db"},
        {"id": "chuanyu",    "rg_db": "data/rg-chuanyu.db",    "rt_db": "data/rt-chuanyu.db"},
        {"id": "shangannin","rg_db": "data/rg-shangannin.db","rt_db": "data/rt-shangannin.db"}
    ],
    "active": "shangannin",
    "recent": ["shangannin", "chuanyu", "xinjiang", "shanghai"]
}
```

所有代码通过 `config.py` 解析当前激活图的 DB 路径，无需修改各模块。

### 四库关系

| 库 | 来源 | 更新频率 | 说明 |
|----|------|----------|------|
| `kl.db` | jprailfan.com | 几个月 | 不可修改 |
| `cc.db` | 路路通 APK | 经常 | 不可修改 |
| `rg.db` | 手工维护 | 按需 | 几何 + 经由，从 kl 设计 |
| `rt.db` | 匹配引擎生成 | 按需 | 车次 + 匹配结果，从 cc + rg 生成 |

每个库含 `meta` 表记录版本和来源关联。所有里程/距离字段统一为 `INTEGER`，无 `REAL`。

## 三铁律

1. 时刻表数据（cc.db）不可修改
2. 客里表数据（kl.db）不可修改
3. 经由表数据只能来自客里表，**绝对不允许用时刻表数据修正经由表**，反之亦然

## 匹配引擎

`tools/match_trains.py` — 精确距离匹配（abs=0）：

| 匹配类型 | 条件 |
|----------|------|
| 正向全匹配 | 起点=经由起点，终点=经由终点，距离差=0 |
| 反向全匹配 | 同上，方向相反 |
| 部分匹配（端点） | 一端=经由端点，另一端在经由上，距离差=0 |
| 部分匹配（中间段） | 两端都在经由中间，距离差=0 |
| 0km 降级匹配 | 站名连续序列匹配（旅游列车等） |

## GUI 功能

### 菜单栏

```
文件(&F)        经由(&R)           工具(&T)         设置(&S)         帮助(&H)
  打开...        经由维护...        更新时刻表...      ✓ 自动备份       关于
  保存            ────────          更新里程表...      删除备份文件...
  另存为...       车次匹配...
  ────────        ────────
  导入 JSON...    经由匹配的车次
  导出 JSON...    车次匹配的经由
```

- **经由维护**：新增/删除/重命名/延伸/修剪经由，内置 经由↔️车次匹配 按钮
- **车次匹配**：跑匹配引擎 → 写入 rt.db → 弹出进度+分类汇总（图外/0km/图内未匹配/图内未匹配区段）
- **经由匹配的车次**：左经由列表 → 右匹配车次，双击弹车次详情
- **车次匹配的经由**：全匹配结果一览，可切换"只显示0匹配"，图内未匹配区段弹窗
- **自动备份**：启动时将 4 库复制到 `data/backup/`（时间戳命名），保留最近 20 版
- **删除备份文件**：多选对话框批量删除

### 主窗口
- 线路图绘制：区间渲染（黑中线 + 红上行 + 绿下行）+ 站名标注
- 选中高亮：path 表选中或画布单击 → 红色加粗高亮对应线路
- 数据面板：线路表（9列）、区间表（6列），表格编辑实时反映
- 画布缩放：+/-/# 按钮
- 拼音跳转：线路选择列表上方 ABCDE/FGH/.../YZ 按钮快速定位
- 头部/尾部延伸：从客里表选站延伸区间，自动计算里程
- 导出/导入 JSON：含 routes + route_stations

## 项目结构

```text
running_train/
├── main.py                  # 入口
├── main_window.py           # 主窗口（UI + 交互 + 菜单 + 备份 + 模拟集成）
├── models.py                # 数据模型 + DB I/O + JSON I/O
├── canvas.py                # 画布（轨道绘制 + 列车绘制）
├── delegates.py             # 单选委托（空心/实心圆）
├── config.py                # 配置管理（图切换 + DB路径 + setup 读写）
├── simulation.py            # 模拟引擎（RouteTrackIndex + TrainPositioner + Clock + Renderer）
├── sim_controls.py          # 模拟控制面板（启停合一 + 步进 + 速度）
├── station_status.py        # 车站状态面板（站内列车实时列表 + 类型形状）
├── route_editor.py          # 经由编辑对话框
├── route_finder.py          # BFS 路径搜索
├── train_match_dialogs.py   # 匹配查看对话框（3 类）
├── requirements.txt
├── README.md
├── CLAUDE.md                # AI 协作方法论
├── .gitignore
├── data/
│   ├── kl.db, cc.db, rg-*.db, rt-*.db
│   ├── kl_revisions.md
│   ├── 数据结构.md
│   ├── backup/              # 自动备份（gitignore）
│   └── old/                 # 归档（gitignore）
└── tools/
    ├── match_trains.py      # 匹配引擎 + 进度对话框
    ├── migrate_to_new_dbs.py# 4-DB 迁移脚本
    ├── migrate_json_to_db.py# JSON→DB 迁移脚本
    ├── parse_llt_apk.py     # APK 时刻表解析
    ├── import_csv_to_json.py# CSV 导入（支持 DB 输出）
    ├── add_route*.py        # 新增经由
    ├── fix_route*.py        # 修正经由
    ├── check_route51.py     # 排查经由偏差
    └── ...
```

## 模拟模块

基于经由匹配数据的列车运行模拟，实现在运行图上实时动态展示车次：

| 特性 | 说明 |
|------|------|
| 时钟 | QTimer 30fps，0-1439 分钟循环，启动时取系统当前时间 |
| 速度 | ½× / 1× / 2× / 4× / 8× 五档 |
| 定位 | RouteTrackIndex（经由站序→track 预计算映射）+ 时间比例线性插值 |
| 上下行 | 每 track 可独立设置上下行罗盘方向（N/E/S/W 四向，默认上行 N / 下行 S） |
| 车次号 | 标签相对圆点的方向由 track 的罗盘方向决定；圆点垂直轨道偏移（上行 +10px，下行 -10px） |
| 控制面板 | 左侧 100px，24 整点按钮 + 时钟 + 步进按钮（⏪10 / ◀1 / 1▶ / 10⏩）+ 开始/暂停 + 速度 |
| 车站状态 | 控制面板下方，下拉框选站（按经停车次排序）+ 站内列车列表（始发/终到/经停，6 种方向形状） |
| 定位算法 | 车次 → train_route_matches → RouteTrackIndex.get_tracks_between() → track 序列 + 线性插值 |

### 定位覆盖率

| 指标 | 上海 | 新疆 |
|------|------|------|
| 加载车次 | 2,528 | 618 |
| 匹配上车次 | 2,302 (91.1%) | 561 (90.8%) |
| 全匹配车次 | 399（所有区段均匹配） | — |
| 部分匹配车次 | 1,903（至少一个区段匹配） | — |
| 零匹配车次 | 226 | 57 |

> RouteTrackIndex 为每条经由预计算所有相邻站序对→图内 track 序列。跨线接续站对（同站不同线、距离 0）自动跳过。隐藏 path 参与匹配但不绘制列车。

## 安装与运行

```bash
pip install -r requirements.txt
python main.py
```

## 更新记录

详见 [UPDATES.md](UPDATES.md)
