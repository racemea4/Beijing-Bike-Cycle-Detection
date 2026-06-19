#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模拟 OSM 风格路网生成器（直接输出 GraphML + HTML）

功能：
- 生成一个网格状 + 随机斜路的模拟路网图
- 随机分配部分节点为红绿灯节点
- 支持通过命令行参数或脚本顶部配置调整路网规模
- 直接输出 GraphML 文件（可用于 search_cycles.py）
- 同时生成一个无外部底图的纯路网 HTML 地图
- 适合快速测试环检测算法，无需下载真实 OSM 数据

用法：
    # 使用默认参数
    python src/generate_osm_like_network.py
    
    # 自定义参数
    python src/generate_osm_like_network.py --grid-x 30 --grid-y 30 --tl-ratio 0.05
    python src/generate_osm_like_network.py --grid-x 10 --grid-y 10 --spacing 0.01
"""

import os
import sys
import random
import math
import argparse
import networkx as nx
import numpy as np
import folium
from folium import plugins

# ==================== 默认配置 ====================
DEFAULT_GRID_X = 25          # 网格列数（控制节点密度）
DEFAULT_GRID_Y = 25          # 网格行数（控制节点密度）
DEFAULT_SPACING = 0.005      # 网格间距（度），约 500 米
DEFAULT_NOISE = 0.001        # 节点位置随机偏移（度）
DEFAULT_EDGE_PROB = 0.85     # 相邻节点之间连接概率
DEFAULT_DIAG_PROB = 0.15     # 对角线连接概率
DEFAULT_TL_RATIO = 0.04      # 红绿灯节点比例（0.01 = 1%）
DEFAULT_RANDOM_SEED = 42     # 固定随机种子，保证可复现
# ===============================================


def generate_simulated_network(grid_x, grid_y, spacing, noise, edge_prob, diag_prob, tl_ratio, seed):
    """
    生成模拟路网图，返回 Graph 和节点坐标字典
    
    参数：
        grid_x, grid_y: 网格行列数
        spacing: 网格间距（度）
        noise: 节点随机偏移量（度）
        edge_prob: 相邻节点连接概率
        diag_prob: 对角线连接概率
        tl_ratio: 红绿灯节点比例
        seed: 随机种子
    
    返回：
        G: NetworkX 图
        pos: 节点坐标字典 {node: (x, y)}
    """
    random.seed(seed)
    np.random.seed(seed)

    # 1. 生成网格节点
    nodes = []
    for ix in range(grid_x):
        for iy in range(grid_y):
            x = ix * spacing + random.uniform(-noise, noise)
            y = iy * spacing + random.uniform(-noise, noise)
            nodes.append((x, y))

    # 2. 构建无向图
    G = nx.Graph()
    for i, (x, y) in enumerate(nodes):
        G.add_node(i, x=x, y=y)

    # 3. 添加边
    for ix in range(grid_x):
        for iy in range(grid_y):
            idx = ix * grid_y + iy
            # 右邻居
            if ix < grid_x - 1:
                jdx = (ix + 1) * grid_y + iy
                if random.random() < edge_prob:
                    G.add_edge(idx, jdx)
            # 上邻居
            if iy < grid_y - 1:
                jdx = ix * grid_y + (iy + 1)
                if random.random() < edge_prob:
                    G.add_edge(idx, jdx)
            # 对角线（右下）
            if ix < grid_x - 1 and iy < grid_y - 1:
                jdx = (ix + 1) * grid_y + (iy + 1)
                if random.random() < diag_prob:
                    G.add_edge(idx, jdx)
            # 对角线（右上）
            if ix < grid_x - 1 and iy > 0:
                jdx = (ix + 1) * grid_y + (iy - 1)
                if random.random() < diag_prob:
                    G.add_edge(idx, jdx)

    # 4. 移除孤立节点
    isolated = [n for n in G.nodes if G.degree(n) == 0]
    G.remove_nodes_from(isolated)

    # 5. 重新编号节点
    mapping = {old: new for new, old in enumerate(sorted(G.nodes))}
    G = nx.relabel_nodes(G, mapping)
    pos = {mapping[old]: (G.nodes[mapping[old]]['x'], G.nodes[mapping[old]]['y']) for old in mapping}

    # 6. 随机分配红绿灯
    num_tl = max(1, int(len(G.nodes) * tl_ratio))
    tl_nodes = random.sample(list(G.nodes), min(num_tl, len(G.nodes)))
    for n in G.nodes:
        G.nodes[n]['has_traffic_light'] = (n in tl_nodes)

    # 7. 计算每条边的长度（米）
    for u, v in G.edges:
        x1, y1 = G.nodes[u]['x'], G.nodes[u]['y']
        x2, y2 = G.nodes[v]['x'], G.nodes[v]['y']
        dist_m = math.hypot((x2 - x1) * 111000, (y2 - y1) * 111000)
        G[u][v]['len_m'] = max(dist_m, 1.0)  # 避免零长度边

    return G, pos


def save_graphml(G, path):
    """保存为 GraphML 文件"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 清理 geometry 属性（NetworkX 保存 GraphML 时某些类型不支持）
    for n in G.nodes:
        G.nodes[n].pop('geometry', None)
    for u, v in G.edges:
        G[u][v].pop('geometry', None)
    nx.write_graphml(G, path)
    print(f"✅ GraphML 已保存: {path}")


def save_html_map(G, pos, path):
    """生成无外部底图的纯路网 HTML 地图"""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 计算边界
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2

    # 自动缩放
    width_deg = max_x - min_x
    height_deg = max_y - min_y
    max_deg = max(width_deg, height_deg)
    if max_deg < 0.001:
        zoom_start = 15
    elif max_deg < 0.005:
        zoom_start = 13
    elif max_deg < 0.02:
        zoom_start = 11
    else:
        zoom_start = 9

    # 创建地图：tiles=None，无任何底图
    m = folium.Map(
        location=[center_y, center_x],
        zoom_start=zoom_start,
        tiles=None,
        control_scale=False
    )

    # 用 CSS 强制设置纯白背景（不依赖 TileLayer）
    m.get_root().header.add_child(folium.Element("""
        <style>
            .leaflet-container {
                background: #ffffff !important;
            }
            .leaflet-tile-pane {
                display: none !important;
            }
        </style>
    """))

    # 绘制边
    for u, v in G.edges:
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        folium.PolyLine(
            [(y1, x1), (y2, x2)],
            color='#555555',
            weight=2,
            opacity=0.8
        ).add_to(m)

    # 绘制节点
    for n, (x, y) in pos.items():
        is_tl = G.nodes[n].get('has_traffic_light', False)
        color = '#e74c3c' if is_tl else '#3498db'
        size = 5 if is_tl else 3
        folium.CircleMarker(
            location=[y, x],
            radius=size,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=f"节点 {n}" + (" 🚦" if is_tl else "")
        ).add_to(m)

    # 图例
    legend_html = f"""
    <div style="position: fixed; bottom: 30px; right: 30px; 
                background: white; padding: 10px 15px; 
                border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                font-family: Arial, sans-serif; font-size: 13px; z-index: 1000;">
        <div><span style="display:inline-block; width:12px; height:12px; background:#3498db; border-radius:50%; margin-right:8px;"></span>普通节点</div>
        <div><span style="display:inline-block; width:12px; height:12px; background:#e74c3c; border-radius:50%; margin-right:8px;"></span>红绿灯节点</div>
        <div><span style="display:inline-block; width:20px; height:3px; background:#555555; margin-right:8px;"></span>道路边</div>
        <div style="margin-top:5px; font-size:11px; color:#888;">节点: {G.number_of_nodes()} | 边: {G.number_of_edges()}</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    plugins.Fullscreen().add_to(m)
    m.save(path)
    print(f"✅ 纯路网地图（无外部底图）已保存: {path}")


def main():
    """主程序入口，支持命令行参数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='生成模拟 OSM 路网数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 使用默认参数
  python generate_osm_like_network.py
  
  # 生成密集路网（更多节点）
  python generate_osm_like_network.py --grid-x 40 --grid-y 40
  
  # 生成稀疏路网（更少节点）
  python generate_osm_like_network.py --grid-x 10 --grid-y 10
  
  # 增加红绿灯比例
  python generate_osm_like_network.py --tl-ratio 0.08
  
  # 自定义输出路径
  python generate_osm_like_network.py --output-data data/my_network.graphml
        """
    )
    parser.add_argument('--grid-x', type=int, default=DEFAULT_GRID_X,
                        help=f'网格列数（默认 {DEFAULT_GRID_X}）')
    parser.add_argument('--grid-y', type=int, default=DEFAULT_GRID_Y,
                        help=f'网格行数（默认 {DEFAULT_GRID_Y}）')
    parser.add_argument('--spacing', type=float, default=DEFAULT_SPACING,
                        help=f'网格间距（度），默认 {DEFAULT_SPACING}')
    parser.add_argument('--tl-ratio', type=float, default=DEFAULT_TL_RATIO,
                        help=f'红绿灯节点比例，默认 {DEFAULT_TL_RATIO}（即 4%）')
    parser.add_argument('--edge-prob', type=float, default=DEFAULT_EDGE_PROB,
                        help=f'边连接概率，默认 {DEFAULT_EDGE_PROB}')
    parser.add_argument('--seed', type=int, default=DEFAULT_RANDOM_SEED,
                        help=f'随机种子，默认 {DEFAULT_RANDOM_SEED}')
    parser.add_argument('--output-data', type=str, default='./data/test_city/simulated_network.graphml',
                        help='GraphML 输出路径')
    parser.add_argument('--output-html', type=str, default='./output/simulated_network_map.html',
                        help='HTML 地图输出路径')

    args = parser.parse_args()

    # 打印配置
    print("=" * 60)
    print("模拟 OSM 路网生成器（直接输出 GraphML + HTML）")
    print("=" * 60)
    print(f"网格大小: {args.grid_x} × {args.grid_y} = {args.grid_x * args.grid_y} 个节点（含随机丢弃）")
    print(f"网格间距: {args.spacing} 度")
    print(f"红绿灯比例: {args.tl_ratio * 100:.1f}%")
    print(f"随机种子: {args.seed}")
    print("-" * 60)

    # 生成图
    G, pos = generate_simulated_network(
        grid_x=args.grid_x,
        grid_y=args.grid_y,
        spacing=args.spacing,
        noise=DEFAULT_NOISE,
        edge_prob=args.edge_prob,
        diag_prob=DEFAULT_DIAG_PROB,
        tl_ratio=args.tl_ratio,
        seed=args.seed
    )

    tl_count = sum(1 for n in G.nodes if G.nodes[n].get('has_traffic_light', False))
    print(f"生成的图: {G.number_of_nodes()} 个节点, {G.number_of_edges()} 条边")
    print(f"红绿灯节点: {tl_count} 个 ({tl_count / G.number_of_nodes() * 100:.1f}%)")

    # 保存
    save_graphml(G, args.output_data)
    save_html_map(G, pos, args.output_html)

    # 完成提示
    print("-" * 60)
    print("🎉 生成完成！")
    print(f"GraphML 文件: {args.output_data}")
    print(f"HTML 地图: {args.output_html}")
    print("\n下一步：运行环路搜索")
    print(f"  python src/search_cycles.py")
    print(f"  输入 GraphML 路径: {args.output_data}")
    print("  输入任意起点坐标（如 0.05, 0.05）")
    print("  设置环长范围（如 1 ~ 50 公里）")
    print("=" * 60)


if __name__ == "__main__":
    main()
