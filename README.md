# 自行车骑行环路检测
> 数算B课程大作业 检测图中有无特定环路
> 在城市路网中自动发现无红绿灯、适合骑行的顺畅环路

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![OSM](https://img.shields.io/badge/Data-OpenStreetMap-orange.svg)](https://www.openstreetmap.org/)

---

## 📖 项目概述

城市道路中存在大量红绿灯，自行车骑行过程中频繁遇到等红灯的情况，无法实现顺畅的骑行体验。然而，城市路网中存在一些**环形路线**，可以规避红绿灯，实现不间断骑行。

本项目基于 **OpenStreetMap（OSM）** 路网数据，通过图论方法自动提取**无红绿灯、适合骑行、形态顺畅的环形路线**。

### 🌍 通用性说明

**本代码不限于特定城市**，可处理任意城市的 OSM 路网数据（北京、上海、东京、洛杉矶、伦敦等）。只需提供对应城市的道路数据，即可运行完整的环路检测流程。

### 🎯 核心问题

> 如何从任意城市的路网图中，自动筛选出**没有红绿灯、长度适中、转弯平滑**的骑行环路？

### 💡 解决方案概述

1. **路网简化**：通过聚类合并、度2节点压缩、剪枝等操作，将原始路网从数万节点压缩至数千节点
2. **红绿灯标记**：匹配 OSM 红绿灯点位，标记到最近的图节点
3. **环路搜索**：基于 `cycle_basis` 提取所有基础环，按长度、顺畅度、距离等多维度排序
4. **顺畅度评分**：综合角度平滑度、边长均匀性、圆度等指标，量化评价环路的骑行体验

---

## 🗺️ 效果预览

<!-- 替换为你的实际截图路径 -->
![简化后路网]([<img width="2879" height="1477" alt="graph_simplified png" src="https://github.com/user-attachments/assets/1b212d43-874b-45a0-b5a4-9fa4a509b1b4" />
])
*图1：简化后的北京大学附近路网*

![环路检测结果]([<img width="2879" height="1254" alt="cycle_map png" src="https://github.com/user-attachments/assets/a19fe0d7-5028-4064-9517-2ac1751ee1ce" />
])
*图2：检测出的骑行环路*

---

## 🏗️ 项目结构

```
Beijing-Bike-Cycle-Detection/
├── README.md
├── LICENSE
├── requirements.txt
│
├── src/
│   ├── build_road_network.py        # 路网构建与简化
│   ├── search_cycles.py             # 带排序功能的环路搜索
│   ├── search_composite.py          # 带综合排序功能的环路搜索
│   ├── generate_osm_like_network.py # 模拟OSM数据生成
│   └── download_city_roads.py       # 城市道路预下载
│
├── data/                            # 用户数据存放位置
├── output/                          # 输出结果
│
└── tools/                           # 附录：辅助工具
    └── pdf_translate_watcher.py     # 论文翻译工具
```

---

## 💻 运行环境推荐

本项目所有命令均建议在 **Visual Studio Code 终端** 中执行。

### 安装 VSCode

**推荐方式（官方下载）**：
- 访问 [code.visualstudio.com](https://code.visualstudio.com/)
- 点击 "Download for Windows" 下载安装包
- 运行安装程序，勾选 "Add to PATH" 方便后续使用

**备选方式（命令行，需网络）**：

```bash
# Windows (使用 winget)
winget install Microsoft.VisualStudioCode

# macOS (使用 Homebrew)
brew install --cask visual-studio-code

# Linux (使用 snap)
sudo snap install code --classic
```

### 快速打开 VSCode 终端

1. 用 VSCode 打开本项目文件夹
2. 按 `` Ctrl + ` ``（Mac: `` Cmd + ` ``）打开终端
3. 终端会自动定位到项目根目录，所有命令可直接运行

---

## ⚙️ 第一部分：路网构建

### 一：现实路网（从 OSM 数据构建）

#### 数据准备 —— 获取道路数据

本项目的核心处理脚本 `build_road_network.py` **只读取本地文件**，不进行网络下载。因此你需要先准备好目标城市的道路数据。

本项目的道路数据来自 **OpenStreetMap（OSM）**，一个全球开源的地图数据库。以下提供四种获取方式：

---

**方式一：使用预先准备的数据（推荐，最省时）**

我们已在 `data/beijing/` 文件夹中预先提供了北京市部分路网数据，你可以直接使用，无需额外下载。

如需使用其他城市的数据，请参考以下方式。

---

**方式二：从 Geofabrik 下载（稳定可靠）**

[Geofabrik](https://download.geofabrik.de/) 提供 OSM 数据的定期归档，下载稳定且可离线使用。

**操作步骤**：

1. 访问 [Geofabrik](https://download.geofabrik.de/)
2. 依次选择：亚洲（Asia）→ 中国（China）→ 北京（Beijing）
3. 下载 `beijing-latest-free.shp.zip` 文件
4. 解压后**仅提取道路图层文件**（文件名含 `roads` 的 `.shp`、`.shx`、`.dbf`、`.prj` 文件）
5. 将提取的文件放入项目的 `data/your_city/` 文件夹中

> ⚠️ **注意**：请勿将建筑物、水系等其他图层放入数据文件夹，以免影响程序识别。

---

**方式三：通过脚本自动下载（网络原因不建议）**

使用项目提供的 `src/download_city_roads.py` 脚本，通过 OSMnx 库直接从 OSM 服务器获取最新数据。

在项目根目录下打开 VSCode 终端，运行：

```bash
python src/download_city_roads.py
```

脚本会交互式地引导你完成下载：

```
============================================================
🌍 OSM 道路数据预下载工具
============================================================
请输入城市名称（例如：Beijing, China）: Beijing, China
请输入输出文件夹（默认 ./data/Beijing）: 

📥 正在从 OSM 下载 Beijing, China 的道路数据...
   道路类型: 19 种（含 residential, tertiary, secondary 等）
   输出目录: ./data/Beijing
...
✅ 下载成功！
   文件路径: ./data/Beijing/Beijing_roads.shp
   道路数量: 48251 条
   文件大小: 78.3 MB
```

**城市示例**：

| 城市 | 输入内容 |
|------|----------|
| 北京 | `Beijing, China` |
| 上海 | `Shanghai, China` |
| 东京 | `Tokyo, Japan` |
| 洛杉矶 | `Los Angeles, USA` |
| 伦敦 | `London, UK` |

> 💡 **提示**：下载时间取决于城市大小和网络速度。建议首次测试时使用较小的城市或区域。

---

**方式四：自己生成模拟路网数据（算法测试）**
无需真实 OSM 数据，直接在本地生成模拟路网，格式与真实数据完全兼容。

**适用场景**：

- 在下载完整 OSM 数据前快速验证算法
- 调参时避免反复加载大文件
- 网络条件不佳时仍可继续开发
- 可重复的单元测试和调试

---

#### 快速生成（使用默认参数）

```bash
python src/generate_osm_like_network.py
```

生成两个文件：

| 文件 | 位置 | 用途 |
|------|------|------|
| `simulated_network.graphml` | `data/test_city/` | **图数据**，给 `search_cycles.py` 读取 |
| `simulated_network_map.html` | `output/` | **可视化地图**，浏览器查看 |

---

#### 自定义参数（命令行）

通过命令行参数灵活控制路网规模：

```bash
# 生成密集路网（更多节点，更多环）
python src/generate_osm_like_network.py --grid-x 40 --grid-y 40

# 生成稀疏路网（更少节点）
python src/generate_osm_like_network.py --grid-x 10 --grid-y 10

# 增加红绿灯节点比例（默认 4%）
python src/generate_osm_like_network.py --tl-ratio 0.08

# 调整网格间距（度），间距越大路网范围越大
python src/generate_osm_like_network.py --spacing 0.01

# 组合使用
python src/generate_osm_like_network.py --grid-x 30 --grid-y 30 --tl-ratio 0.05 --spacing 0.008
```

**所有可用参数**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--grid-x` | 网格列数 | 25 |
| `--grid-y` | 网格行数 | 25 |
| `--spacing` | 网格间距（度），约 0.005° ≈ 500 米 | 0.005 |
| `--tl-ratio` | 红绿灯节点比例（0.04 = 4%） | 0.04 |
| `--edge-prob` | 相邻节点连接概率 | 0.85 |
| `--seed` | 随机种子（固定保证可复现） | 42 |
| `--output-data` | GraphML 输出路径 | `./data/test_city/simulated_network.graphml` |
| `--output-html` | HTML 地图输出路径 | `./output/simulated_network_map.html` |

> 💡 **提示**：`--grid-x` 和 `--grid-y` 直接影响节点数量。默认 25×25 = 625 个网格节点（经随机丢弃后约 500 个），路网密度适中，运行速度快。如需更多环路，可增大网格。

---

#### 完整工作流示例

```bash
# 1. 生成一个 30×30 的密集路网
python src/generate_osm_like_network.py --grid-x 30 --grid-y 30 --tl-ratio 0.05

# 2. 运行环路搜索（注意：输入 .graphml 文件）
python src/search_cycles.py
# 输入图路径: data/test_city/simulated_network.graphml
# 起始点经度: 0.05
# 起始点纬度: 0.05
# 最短环长度: 1
# 最长环长度: 50
# 最大距离: 100

# 3. 在浏览器中打开 output/cycles_map_final.html 查看结果
```

#### 手动放置已有数据

如果你已经拥有 OSM 格式的 Shapefile 数据（`.shp` 文件），可直接将其放入 `data/` 下的任意子文件夹：

```
data/
└── your_city/
    ├── your_city_roads.shp
    ├── your_city_roads.shx
    └── your_city_roads.dbf
```

然后直接运行 `build_road_network.py`，输入该文件夹路径即可。

> ⚠️ **注意**：程序会扫描文件夹内所有 `.shp` 文件并自动识别道路图层，请确保文件夹内只放置道路数据，避免混入建筑物、水系等其他图层。

---

#### 处理路网数据

**文件**：`src/build_road_network.py`

准备好数据后，运行主程序处理数据：

在项目根目录下打开 VSCode 终端：

```bash
python src/build_road_network.py
# 根据提示输入刚才下载的数据文件夹路径
# 例如：./data/Beijing
# 裁剪范围可直接回车使用全量数据
```

**处理步骤**：

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 读取 OSM 道路图层 | 筛选 `fclass` / `highway` 为自行车道类型 |
| 2 | 匹配红绿灯点位 | 将红绿灯点标记到最近节点 |
| 3 | 投影到米制坐标系 | EPSG:3857，便于计算实际距离 |
| 4 | 短边聚类合并 | 距离 < 30m 的节点合并，红绿灯节点优先保留 |
| 5 | 度2节点简化 | 移除度数=2且非红绿灯的节点，拉直道路 |
| 6 | 剪枝 | 移除度 ≤ 1 的叶子节点（死胡同） |
| 7 | 反投影回 WGS84 | 恢复经纬度坐标 |

**支持的数据格式**：

- **输入**：OSM 导出的 Shapefile（含 `.shp`, `.shx`, `.dbf`, `.prj`）
- **输出**：`.graphml` 格式图文件 + Folium HTML 地图

---

### 二：模拟路网（用于算法测试）

**文件**：`src/generate_osm_like_network.py`

> 💡 此脚本已在【方式四】中介绍，如需快速测试算法而无需真实数据，可直接使用。

**参数配置**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `center_lon` / `center_lat` | 116.4, 39.9 | 模拟城市中心经纬度 |
| `size_km` | 5 | 模拟区域大小（公里） |
| `grid_spacing_km` | 0.3 | 道路网格间距（公里） |

**使用示例**：

```bash
# 在 VSCode 终端中运行
python src/generate_osm_like_network.py
# 生成 data/test_city/test_roads.shp
# 可直接用 build_road_network.py 读取处理
```

---

## 🔍 第二部分：环路搜索与排序

**文件**：`src/search_cycles.py`、`src/search_composite.py`

### 核心算法：顺畅度评分

从简化后的路网中提取所有基础环，按以下维度综合评价：

| 维度 | 权重 | 评分逻辑 |
|------|------|----------|
| **角度平滑度** | 30% | 转弯角度越接近 180° 分越高 |
| **大角度比例** | 20% | 角度 > 150° 的节点占比越高分越高 |
| **边长均匀性** | 20% | 边长变异系数越小分越高 |
| **圆度** | 30% | 几何形状越接近圆形分越高 |
| **锐角惩罚** | - | 角度 < 10° 的节点每个扣 5 分 |

### 搜索维度

用户可通过交互式输入控制搜索条件：

- **起始点**：环路上必须包含靠近该点的节点
- **长度范围**：例如 5~30 公里
- **搜索半径**：环距离起始点的最大距离
- **排序方式**：按长度 / 顺畅度 / 距离 / 综合得分

### 使用示例

```bash
# 在 VSCode 终端中运行
python src/search_cycles.py
# 输入 .graphml 路径、起点经纬度、环长范围
# 生成 cycles_map_final.html 交互式地图
```

---

## 🚀 快速开始（5 分钟体验）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 生成测试数据（无需下载 OSM）

```bash
python src/generate_osm_like_network.py
```

### 3. 运行环检测

```bash
python src/search_cycles.py
# 输入 output_full/final_simplified.graphml
# 输入起点坐标（如 0 0）
```

### 4. 查看结果

在浏览器中打开 `output_full/cycles_map_final.html`

---

## 📚 课程对应

| 课程模块 | 本项目应用 |
|----------|-----------|
| 图的基本概念 | 路网建模为无向图 |
| 图遍历 | DFS/BFS 用于连通分量提取 |
| 图简化 | 度2节点压缩、剪枝 |
| 图算法 | `cycle_basis` 环提取 |

---

## 🛠️ 附录：论文翻译工具配置与使用指南

> 本工具为寻找大作业思路过程中顺便搭建的独立功能，不依赖主项目，为了防止大作业内容过于单薄还是写上（
> 用于监控指定文件夹，自动翻译新放入的 PDF 论文。

**文件位置**：`tools/pdf_translate_watcher.py`（已包含在仓库中）

### 📌 工具概述

该脚本基于 `pdf2zh`（PDFMathTranslate）和 DeepSeek API，实现：

- 自动监控桌面「英文论文」文件夹
- 新 PDF 放入后自动翻译（中英对照）
- 翻译结果自动归类到「论文翻译」文件夹
- 支持术语表导出
### 1️⃣ 环境准备

#### 安装主体项目依赖（必须）

翻译工具是独立功能，**不依赖**主项目的核心依赖。如果你只需要使用路网构建与环路搜索功能，只需安装以下基础依赖：

```bash
pip install -r requirements.txt
```

> 💡 该文件已包含 `geopandas`、`networkx`、`shapely`、`folium` 等必需库，**不包含** `watchdog` 和 `pdf2zh`。

---

#### 安装翻译工具额外依赖（可选）

如果你**不需要**使用论文翻译工具（`tools/pdf_translate_watcher.py`），可以跳过此步骤，不影响主体项目的任何功能。

如需使用翻译工具，请额外安装以下依赖：

```bash
pip install watchdog pdf2zh
```

> 如果 `pdf2zh` 安装失败，可参考官方仓库：https://github.com/Byaidu/PDFMathTranslate

---

#### 获取 DeepSeek API Key

翻译工具需要调用 DeepSeek API，访问 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 注册并获取 API Key（仅在首次运行翻译工具时使用）。

### 2️⃣ 脚本位置

该脚本**已包含在仓库中**，位于项目目录下的 `tools/pdf_translate_watcher.py`。

你无需手动创建或移动任何文件，克隆/下载本仓库后，该脚本即位于正确位置：

```
Beijing-Bike-Cycle-Detection/
└── tools/
    └── pdf_translate_watcher.py   ← 已存在，直接使用
```

> 💡 **提示**：所有代码都在仓库里，你只需在项目根目录下打开 VSCode 终端，直接运行 `python tools/pdf_translate_watcher.py` 即可。

---

### 3️⃣ 首次运行（自动配置）

在项目根目录下执行：

```bash
python tools/pdf_translate_watcher.py
```

脚本会自动执行以下操作：

| 操作 | 说明 |
|------|------|
| **创建文件夹** | 在桌面自动创建「英文论文」「论文翻译」「临时处理论文」三个文件夹 |
| **检测 pdf2zh** | 自动搜索 `~/pdf2zh-env/Scripts/pdf2zh_next.exe`（默认虚拟环境路径） |
| **提示输入 API Key** | 首次运行会交互式引导输入 DeepSeek API Key，并保存到配置文件 |

运行效果示例：

```
============================================================
📄 PDF 自动翻译监控工具
============================================================
📁 已在桌面创建以下文件夹：
   - C:\Users\你的用户名\Desktop\英文论文
   - C:\Users\你的用户名\Desktop\论文翻译
   - C:\Users\你的用户名\Desktop\临时处理论文

============================================================
🔑 首次运行需要设置 DeepSeek API Key
============================================================
请前往 https://platform.deepseek.com/api_keys 获取
------------------------------------------------------------
请输入你的 DeepSeek API Key:
确认保存？(y/n): y
✅ API Key 已保存至: ...\.pdf_translate_config.json

⚠️ 未找到 pdf2zh: C:\Users\你的用户名\pdf2zh-env\Scripts\pdf2zh_next.exe
请确保已安装 pdf2zh...
请输入 pdf2zh_next.exe 的完整路径（直接回车使用默认路径）: 
```

> 💡 **提示**：如果 pdf2zh 安装在非默认位置，根据提示输入完整路径即可。

---

### 4️⃣ 配置管理（常用命令）

#### 重新设置 API Key

```bash
python tools/pdf_translate_watcher.py --set-key
```

#### 重新设置 pdf2zh 路径

```bash
python tools/pdf_translate_watcher.py --set-pdf2zh-path
```

#### 查看当前配置

配置文件保存在脚本同目录下的 `.pdf_translate_config.json`（Windows 下自动隐藏），内容示例：

```json
{
  "deepseek_api_key": "sk-xxxxxxxxxxxxxxxx",
  "pdf2zh_path": "D:\\tools\\pdf2zh\\pdf2zh_next.exe"
}
```

---

### 5️⃣ 日常使用流程

1. **启动监控**：
   ```bash
   python tools/pdf_translate_watcher.py
   ```

2. **放入 PDF**：将需要翻译的英文论文拖入桌面「英文论文」文件夹

3. **自动处理**：
   - 脚本检测到新 PDF 后自动调用翻译引擎
   - 生成 `-mono.pdf`（译文）和 `-dual.pdf`（对照版）
   - 自动移动到「论文翻译」下的子文件夹（以原文件名前10字符命名）

4. **查看结果**：
   - 打开桌面「论文翻译」文件夹
   - 每个 PDF 独立存放在 `原文件名前10字符翻译结果/` 子目录中

---

### 6️⃣ 目录结构说明

```
桌面/
├── 英文论文/                    ← 监控文件夹（放入待翻译 PDF）
│   └── example_paper.pdf
│
├── 临时处理论文/                 ← 翻译过程中的临时文件（自动清理）
│
└── 论文翻译/                    ← 输出根文件夹
    └── example_pap翻译结果/      ← 每个 PDF 独立子文件夹
        ├── example_paper.pdf    ← 原文件
        ├── example_paper-mono.pdf   ← 纯译文
        ├── example_paper-dual.pdf   ← 中英对照
        └── example_paper.zh-CN.glossary.csv  ← 术语表
```

---

### 7️⃣ 常见问题排查

| 问题 | 解决方法 |
|------|----------|
| **`No such file or directory`** | 确保在项目根目录执行命令，且 `tools/pdf_translate_watcher.py` 存在 |
| **`ModuleNotFoundError: No module named 'watchdog'`** | 执行 `pip install watchdog` |
| **`pdf2zh_next.exe` 找不到** | 运行 `python tools/pdf_translate_watcher.py --set-pdf2zh-path` 手动指定路径 |
| **翻译报错 `401 Unauthorized`** | API Key 无效或过期，运行 `--set-key` 重新设置 |
| **翻译后找不到输出文件** | 检查「临时处理论文」文件夹是否有临时文件，确认 `pdf2zh` 本身是否工作正常 |

---

### 8️⃣ 完整命令行参考

| 命令 | 说明 |
|------|------|
| `python tools/pdf_translate_watcher.py` | 正常启动监控 |
| `python tools/pdf_translate_watcher.py --set-key` | 重新设置 DeepSeek API Key |
| `python tools/pdf_translate_watcher.py --set-pdf2zh-path` | 重新设置 pdf2zh 可执行文件路径 |

---

### 9️⃣ 卸载/停止

- **停止监控**：在命令行窗口按 `Ctrl+C` 即可终止监控进程
- **完全卸载**：删除桌面「英文论文」「论文翻译」「临时处理论文」三个文件夹，以及项目中的 `tools/pdf_translate_watcher.py` 和 `.pdf_translate_config.json` 配置文件

---

## 📖 技术栈

| 类别 | 工具 |
|------|------|
| 图处理 | NetworkX |
| 地理数据 | GeoPandas, Shapely |
| 可视化 | Folium, Leaflet.js |
| 数值计算 | NumPy |
| 文件监控 | Watchdog |
| 数据格式 | GraphML, Shapefile |

---

## 📄 License

MIT License - 详见 [LICENSE](LICENSE) 文件
```
---
