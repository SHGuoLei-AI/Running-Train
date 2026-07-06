# Running Train

基于 PySide6 的铁路运行动态模拟工具，支持多图切换。

## 当前状态

| 指标 | 新疆 | 上海 | 川渝 | 陕甘宁 |
|------|------|------|------|--------|
| 图内线路 | 33 path | 39 path | 39 path | 30 path |
| 图内区段 | 250 | 222 | 455 | 446 |
| 图内站 | 238 | 161 | 431 | 410 |
| 经由总数 | 26 | 51 | 47 | 9 |
| 图内车次 | 618 | 2,528 | 1,853 | 61 |

| 客里表线路 | 765 条，6726 站 |
| 时刻表车次 | 17,168 趟，150,841 停站 |
| 客里表修订 | 16 项（[kl_revisions.md](data/kl_revisions.md)） |

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

## 最近更新

### 2026-07-05
- **车站状态面板**：控制面板下方新增车站状态区域，下拉框按经停车次排序选站，实时显示始发/终到/经停列车，6 种方向类型形状（外凸三角/内凹三角/平直）
- **隐藏 path 逐 track 判定**：列车在隐藏 track 上不可见、在可见 track 上正常显示，替代原先全段隐藏逻辑
- **多经由拼接匹配**：`_expand_multi_route` 回退从 route_stations 找接续站，`_get_stop_pair_tracks` 在接续站拼接 track 序列
- **川渝图**：补 20 条联络线 + 重庆东环线为隐藏 path

### 2026-07-04
- **客里表修订 10→15 项**：川青线（棉竹南→绵竹南）、达万线（开江→开江南）站名修正；成灌线（安靖↔成都西）、成都西环线（补入草金所）、宁蓉线（补入童家溪所）、西成客专线（德阳里程修订）、白覃联络线（12→11km）
- **川渝图**：图内未匹配区段 438→5；匹配率 90.7%；路径 15→39，经由 0→47
- **菜单重构**：新增"车次"菜单，导入车次/车次列表移入；车次列表增加"清洗车次"按钮
- **状态栏**：车站名后追加坐标值
- **换图修复**：经由维护/车次列表对话框 DB 路径改为动态获取（不再缓存 import 时常量）
- **_train_info 刷新**：换图/编辑 track 后重新加载起讫站映射

### 2026-06-28
- **川渝图**：新建 川渝（chuanyu）图，含 成渝中线/成达万/新渝万高铁（15 path, 256 tracks）
- **图属性修复**：`train_graph` 表 INSERT OR REPLACE 未清理旧行导致多行并存、属性读取混乱 — 改为 DELETE 后 INSERT；清理 `length`/`width`/`scale` 残留列
- **状态栏增强**：鼠标悬停显示 坐标、线路、车站、车次（允许多个）
- **新建图修复**：`executescript` 不支持参数占位符 `?`，拆分为独立 `execute()` 调用

### 2026-06-25
- **经由匹配定位**：模拟引擎从 BFS 改为 RouteTrackIndex，定位覆盖率 ~91%（~2,302/2,528 车次）
- **匹配引擎修复**：中间站校验（防止如皋南等非经由站在部分匹配中被错误包含）
- **方向系统**：车次标签方向从 8 向简化为 4 向（N/E/S/W），每 track 可独立设置上下行方向
- **客里表修订**：新增 通苏嘉甬高速线（10 站 310km）；补入 钱清/迪荡（杭甬线）、春申/春申所（上海南联络线）
- **经由延伸**：京沪普（林场→南京）、沪昆高（杭州东→杭州南）
- **UI 优化**：控制面板 开始/暂停 合一，新增步进按钮；Path 编辑 头部延伸/尾部延伸/从客里表新增
- **数据清理**：删除不以数字结尾的车次

### 2026-06-20
- **4-DB 架构**：kl.db / cc.db / rg.db / rt.db 分离，完整 schema 文档
- **全 INTEGER 化**：所有里程/距离/坐标/角度字段从 REAL 改为 INTEGER
- **菜单重构**：工具→经由，新增车次匹配、工具、设置菜单
- **自动备份**：启动时备份 4 库到 data/backup/，保留 20 版

### 2026-06-19
- JSON→DB 切换，JSON 仅作交换格式
- 导出/导入包含 routes + route_stations
- 匹配引擎 exact match (abs=0)
- 匹配进度对话框 + 分类汇总
