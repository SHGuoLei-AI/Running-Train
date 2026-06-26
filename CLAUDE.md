# 经由匹配方法论

## 一、数据源与铁律

| 数据 | 来源 | 角色 |
|------|------|------|
| `kl.db` | 客里表 | **唯一里程来源**，不可修改（全局共用） |
| `cc.db` | APK提取 | 时刻表数据，不可修改（全局共用） |
| `rg.db` | 项目库 | 几何结构：经由表、TrainGraph、RailwayTrack（每图独立） |
| `rt.db` | 项目库 | 图上车次：region_trains、train_route_matches（每图独立） |

**图切换机制**：见 `data/graphs.json`。通过菜单 **图(&G)** 切换。所有代码通过 `config.py` 解析当前激活图的 DB 路径。

上海区域归档文件：`rg-shanghai.db` / `rt-shanghai.db`。

**三条铁律：**
1. 时刻表数据不可修改
2. 客里表（kl）数据不可修改
3. 经由表数据只能来自客里表，**绝对不允许用时刻表数据修正经由表**，反之亦然

## 二、经由设计流程

### 1. 确定起讫站
从零匹配车次中找图内OD（图内站 = 出现在 `railway_track` 表 `head_station` 或 `tail_station` 中的车站）。

### 2. 查kl拓扑
```sql
-- 查线路车站
SELECT station_name, dist_from_start, dist_from_prev, is_junction 
FROM line_stations WHERE line_name='线名' ORDER BY dist_from_start

-- 查某站在哪些线路上
SELECT line_name, dist_from_start FROM line_stations WHERE station_name='站名'

-- 查联络线（关键字：联络、接续）
SELECT DISTINCT line_name FROM line_stations WHERE line_name LIKE '%联络%'
```

### 3. 注意联络线
实际车次常走**联络线**而非站内换乘：
- 例：赵甸联络线（南通西→平东所4km）替代 南通西→赵甸站→宁启（绕行6+14km）
- 例：镇江联络线（横山所→镇江12km）替代 连镇→丹徒→沪宁（绕行多6km）
- 例：金山线（春申南所→春申1km）连接 沪春线和沪昆线

### 4. 计算累计里程
- kl的 `dist_from_start` 是线路内从起点算的距离
- 跨线接续时，从上一线路累积 + 本线路里程差（终点dist - 起点dist）
- **不要**用圆整估算值（30、40等），用kl的精确值（39、14、53等）

### 5. 验证
与时刻表车次距离对比，偏差必须 = 0km（精确匹配）。若所有车次一致偏差同一值 → 拓扑路径有误（走了不同线/联络线）。

## 三、匹配引擎逻辑

`tools/match_trains.py`：

### 距离匹配（主要方式）
对每趟车次的每对停站 (i, j)，检查是否落在某条经由上：

| 匹配类型 | 条件 |
|----------|------|
| 正向全匹配 | 起点=经由起点，终点=经由终点，距离差=0 |
| 反向全匹配 | 同上，方向相反 |
| 部分匹配（端点） | 一端=经由端点，另一端在经由上，距离差=0 |
| 部分匹配（中间段） | 两端都在经由中间，距离差=0 |

### 0km降级匹配
当车次所有停站距离全为0（旅游列车等）时，降级为站名连续序列匹配：
- 对每个起点 i，找到最长的连续子序列 `train[i:j+1]` 在某条经由上出现
- 优先最长匹配段

### 中间站校验
所有匹配类型（正向/反向/端点/中间段）均需通过中间停站校验：
```python
all(stops[k][1] in r_dists for k in range(i, j + 1))
```
防止车次通过不在经由上的中间站被错误匹配（如 R11/R13 错误匹配经如皋南区段）。

## 四、排查零匹配方法

1. 查车次实际距离：`train_stops.distance_km` 差值
2. 查kl中相关线路的 `dist_from_start`
3. 逐一对比每个区间，定位里程偏差段
4. 检查是否走了联络线而非站内换乘
5. 修正经由，重新匹配
6. 反复直到该OD所有车次偏差 = 0km

## 五、当前状态

| 指标 | 新疆 | 上海 |
|------|------|------|
| 经由总数 | 20 | 51 |
| 图内站 | 122 | 161 |
| 图内线路 | 25 path | 39 path |
| 图内区段 | 130 | 222 |
| 图内车次 | 493 | 2,528 |

### 模拟模块

| 指标 | 值 |
|------|------|
| 加载车次 | 493 (新疆) / 2,528 (上海) |
| 定位算法 | train_route_matches + RouteTrackIndex |
| 多经由拼接 | 支持，覆盖跨线车次 |

模拟算法：TrainPositioner 使用 `train_route_matches` 中的 matched 区段，通过 RouteTrackIndex 预计算映射将经由站序映射到图内 track 序列，再进行时间比例线性插值。跨线接续站对（同站不同线、距离为 0）自动跳过。隐藏 path 参与匹配但不绘制列车。多经由拼接匹配覆盖跨线车次。

## 六、数据架构

```
data/
├── kl.db             # 客里表 — 756线, 6654站 (jprailfan)
├── cc.db             # 时刻表 — 17168车次, 150841停站 (路路通)
├── rg.db             # 几何结构（当前激活图: 新疆）
├── rt.db             # 图上车次（当前激活图: 新疆）
├── rg-shanghai.db    # 几何结构 — 上海区域归档
├── rt-shanghai.db    # 图上车次 — 上海区域归档
├── graphs.json       # 图配置（多图切换）
├── backup/           # 自动备份 (gitignore)
└── 数据结构.md
```

rg.db 维护：`meta.kl_version` ↔ `kl.db.meta.version`

## 七、相关脚本

| 脚本 | 用途 |
|------|------|
| `tools/match_trains.py` | 匹配引擎，输出CSV + 写入 rt.db |
| `tools/migrate_to_new_dbs.py` | 4-DB 迁移脚本 |
| `tools/parse_llt_apk.py` | APK 时刻表解析 |
| `tools/add_route*.py` | 新增单条经由 |
| `tools/fix_route*.py` | 修正已有经由距离 |
| `tools/check_route51.py` | 检查指定经由的距离偏差 |
| `tools/check_kl_route51.py` | 查询kl线路数据辅助排查 |
| `route_finder.py` | 自动BFS搜索两站间路径（辅助工具） |
| `tools/migrate_json_to_db.py` | JSON→DB 迁移（已执行） |
| `simulation.py` | 模拟引擎：RouteTrackIndex + TrainPositioner + SimulationClock + TrainRenderer |
| `sim_controls.py` | 模拟控制面板 |
| `canvas.py` | 画布：Pass 1(线路) + Pass 2(站名) + Pass 3(列车) |
| `models.py` | 数据模型：TrainGraph、RailwayPath、RailwayTrack（含方向字段） |
