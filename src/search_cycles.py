#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
环路搜索工具（交互式）
输入简化后的 GraphML 文件，自动筛选符合条件的骑行环路。
"""

import os
import json
import networkx as nx
import numpy as np
from tqdm import tqdm
from math import radians, sin, cos, sqrt, asin, degrees
from shapely.geometry import Polygon

# ==================== 全局配置 ====================
# 默认输出目录（与 README 一致）
OUTPUT_DIR = "./output"
# ================================================

def haversine(lon1, lat1, lon2, lat2):
    R = 6371000
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlam/2)**2
    c = 2 * asin(sqrt(a))
    return R * c

def angle_between_edges(prev, curr, nxt, G):
    lon_c = G.nodes[curr]['x']
    lat_c = G.nodes[curr]['y']
    lon_p = G.nodes[prev]['x']
    lat_p = G.nodes[prev]['y']
    lon_n = G.nodes[nxt]['x']
    lat_n = G.nodes[nxt]['y']
    dx1 = (lon_p - lon_c) * 111000 * cos(radians(lat_c))
    dy1 = (lat_p - lat_c) * 111000
    dx2 = (lon_n - lon_c) * 111000 * cos(radians(lat_c))
    dy2 = (lat_n - lat_c) * 111000
    dot = dx1*dx2 + dy1*dy2
    mag1 = np.hypot(dx1, dy1)
    mag2 = np.hypot(dx2, dy2)
    if mag1 == 0 or mag2 == 0:
        return 180.0
    cos_angle = dot / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return degrees(np.arccos(cos_angle))

def compute_smoothness(cycle, G):
    """
    顺畅度评分：
    - 角度偏差（偏离180°的均值），正常化后得分
    - 锐角惩罚：角度<10°的每个节点扣5分，上限扣50分
    - 大角度比例：角度>150°的节点比例越高越好
    - 边长均匀性（变异系数）
    - 圆度
    """
    n = len(cycle)
    angles = []
    sharp_penalty = 0
    large_angle_count = 0
    for i in range(n):
        prev = cycle[(i-1) % n]
        curr = cycle[i]
        nxt = cycle[(i+1) % n]
        angle = angle_between_edges(prev, curr, nxt, G)
        angles.append(angle)
        if angle < 10:
            sharp_penalty += 5
        if angle > 150:
            large_angle_count += 1
    sharp_penalty = min(sharp_penalty, 50)

    devs = [abs(180 - a) for a in angles]
    avg_dev = np.mean(devs) if devs else 0
    norm_dev = min(1.0, avg_dev / 180.0)

    large_ratio = large_angle_count / n if n > 0 else 0
    large_score = large_ratio

    lengths = []
    for i in range(n):
        u = cycle[i]
        v = cycle[(i+1) % n]
        if G.has_edge(u, v):
            l = G[u][v].get('len_m', 0)
        elif G.has_edge(v, u):
            l = G[v][u].get('len_m', 0)
        else:
            l = 0
        lengths.append(l)
    mean_len = np.mean(lengths) if lengths else 1
    std_len = np.std(lengths) if lengths else 0
    cv = std_len / mean_len if mean_len > 0 else 1.0
    norm_cv = min(1.0, cv)

    try:
        coords = [(G.nodes[node]['x'], G.nodes[node]['y']) for node in cycle]
        poly = Polygon(coords)
        area = poly.area
        perim = poly.length
        if perim > 0:
            circularity = 4 * np.pi * area / (perim * perim)
            circularity = min(1.0, max(0.0, circularity))
        else:
            circularity = 0.0
    except:
        circularity = 0.0

    smoothness_base = (1 - norm_dev) * 0.3 + large_score * 0.2 + (1 - norm_cv) * 0.2 + circularity * 0.3
    score = smoothness_base * 100
    score -= sharp_penalty
    score = max(0.0, score)
    return round(score, 1)

def load_graph(path):
    print(f"加载图: {path}")
    G = nx.read_graphml(path)
    for node, data in G.nodes(data=True):
        if 'x' not in data or 'y' not in data:
            coords = node.strip('()').split(', ')
            data['x'] = float(coords[0])
            data['y'] = float(coords[1])
        data['id'] = node
    
    # ========== 新增：显示节点坐标范围 ==========
    if G.number_of_nodes() > 0:
        xs = [data['x'] for _, data in G.nodes(data=True)]
        ys = [data['y'] for _, data in G.nodes(data=True)]
        print(f"节点坐标范围:")
        print(f"  经度: {min(xs):.6f} ~ {max(xs):.6f}")
        print(f"  纬度: {min(ys):.6f} ~ {max(ys):.6f}")
        print(f"  中心点: ({ (min(xs)+max(xs))/2:.6f}, { (min(ys)+max(ys))/2:.6f})")
        print(f"  建议起始点: { (min(xs)+max(xs))/2:.6f}, { (min(ys)+max(ys))/2:.6f}")
    else:
        print("⚠️ 图中没有节点，请检查 GraphML 文件是否包含有效数据")
    # ============================================
    
    print(f"节点: {G.number_of_nodes()}, 边: {G.number_of_edges()}")
    return G


def remove_traffic_lights(G):
    to_remove = [n for n, d in G.nodes(data=True) if d.get('has_traffic_light', False)]
    print(f"移除红绿灯节点: {len(to_remove)}")
    G.remove_nodes_from(to_remove)
    G.remove_nodes_from(list(nx.isolates(G)))
    return G

def main():
    print("="*60)
    print("环路搜索工具（交互式）")
    print("="*60)

    graph_path = input("请输入 GraphML 文件路径: ").strip()
    if not os.path.exists(graph_path):
        print("文件不存在。")
        return

    try:
        start_lon = float(input("起始点经度: ").strip())
        start_lat = float(input("起始点纬度: ").strip())
        min_len_km = float(input("最短环长度（公里）: ").strip())
        max_len_km = float(input("最长环长度（公里）: ").strip())
        max_dist_km = input("环上节点距离起始点最大距离（公里，默认5）: ").strip()
        max_dist_km = float(max_dist_km) if max_dist_km else 5.0
    except ValueError:
        print("输入格式错误。")
        return

    min_len_m = min_len_km * 1000
    max_len_m = max_len_km * 1000
    max_dist_m = max_dist_km * 1000

    G = load_graph(graph_path)
    G = remove_traffic_lights(G)
    if G.number_of_nodes() == 0:
        print("无节点。")
        return

    largest_cc = max(nx.connected_components(G), key=len)
    G = G.subgraph(largest_cc).copy()
    print(f"最大连通分量: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")

    print("计算基础环...")
    cycles = nx.cycle_basis(G)
    print(f"基础环数量: {len(cycles)}")

    good_cycles = []
    for cycle in tqdm(cycles, desc="筛选环"):
        length = 0.0
        for i in range(len(cycle)):
            u = cycle[i]
            v = cycle[(i+1) % len(cycle)]
            if G.has_edge(u, v):
                length += G[u][v].get('len_m', 0)
            elif G.has_edge(v, u):
                length += G[v][u].get('len_m', 0)
            else:
                break
        else:
            if min_len_m <= length <= max_len_m:
                near = any(haversine(start_lon, start_lat, G.nodes[n]['x'], G.nodes[n]['y']) <= max_dist_m for n in cycle)
                if near:
                    good_cycles.append((cycle, length))

    print(f"符合条件的环数量: {len(good_cycles)}")
    if not good_cycles:
        print("没有符合条件的环。")
        return

    cycle_data = []
    for cycle, length in tqdm(good_cycles, desc="计算属性"):
        smooth = compute_smoothness(cycle, G)
        min_dist = min(haversine(start_lon, start_lat, G.nodes[n]['x'], G.nodes[n]['y']) for n in cycle)
        cycle_data.append({
            'cycle': cycle,
            'length_km': length / 1000,
            'smoothness': smooth,
            'min_dist_m': min_dist
        })

    cycle_data.sort(key=lambda x: x['smoothness'], reverse=True)
    total = len(cycle_data)
    print(f"总环数: {total}")
    if total > 0:
        print(f"最高顺畅度: {cycle_data[0]['smoothness']}")

    max_display = 500
    if total > max_display:
        print(f"注意：环数量较多，网页只显示前 {max_display} 个（按顺畅度）。")
        top_cycles = cycle_data[:max_display]
    else:
        top_cycles = cycle_data

    # 构建前端数据
    cycles_geojson = []
    color_palette = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4', '#46f0f0', '#f032e6',
                     '#bcf60c', '#fabebe', '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000', '#aaffc3']
    for idx, data in enumerate(top_cycles):
        cycle = data['cycle']
        nodes_geom = [(G.nodes[n]['x'], G.nodes[n]['y'], n) for n in cycle]
        edges_geom = []
        for i in range(len(cycle)):
            u = cycle[i]
            v = cycle[(i+1) % len(cycle)]
            if G.has_edge(u, v):
                l = G[u][v].get('len_m', 0)
            elif G.has_edge(v, u):
                l = G[v][u].get('len_m', 0)
            else:
                continue
            edges_geom.append({
                'coords': [[G.nodes[u]['y'], G.nodes[u]['x']], [G.nodes[v]['y'], G.nodes[v]['x']]],
                'length_m': l
            })
        cycles_geojson.append({
            'id': idx,
            'length_km': data['length_km'],
            'smoothness': data['smoothness'],
            'min_dist_km': data['min_dist_m'] / 1000,
            'nodes': nodes_geom,
            'edges': edges_geom
        })

    cycles_json_str = json.dumps(cycles_geojson, separators=(',', ':'))
    color_palette_str = json.dumps(color_palette)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>自行车环线地图 - 多维度排序</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        #map {{ height: 600px; }}
        .control-panel {{
            position: absolute; top: 10px; right: 10px; background: white; padding: 10px;
            border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.3); z-index: 1000;
            max-height: 80%; overflow-y: auto; width: 350px;
        }}
        .control-panel h4 {{ margin: 0 0 5px 0; }}
        .control-panel select {{ width: 100%; margin-bottom: 10px; }}
        .control-panel label {{ display: block; margin: 3px 0; font-size: 12px; }}
        .control-panel input {{ margin-right: 5px; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="control-panel">
        <h4>环线列表（共{len(cycles_geojson)}个）</h4>
        <div>
            <label>排序方式:</label>
            <select id="sortSelect">
                <option value="smoothness">按顺畅度 (高->低)</option>
                <option value="length">按长度 (长->短)</option>
                <option value="distance">按距起始点最近距离 (近->远)</option>
            </select>
        </div>
        <div id="checkboxes"></div>
    </div>
    <script>
        var cyclesData = {cycles_json_str};
        var colorPalette = {color_palette_str};

        var map = L.map('map').setView([{start_lat}, {start_lon}], 12);
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> contributors'
        }}).addTo(map);

        var currentLayers = {{}};

        function getColor(idx) {{
            return colorPalette[idx % colorPalette.length];
        }}

        function createLayerGroup(cycle, color) {{
            var edgeLayer = L.layerGroup();
            var nodeLayer = L.layerGroup();
            for (var i=0; i<cycle.edges.length; i++) {{
                var e = cycle.edges[i];
                var poly = L.polyline(e.coords, {{color: color, weight: 3, opacity: 0.8}});
                poly.bindTooltip("长度: " + e.length_m.toFixed(1) + " 米", {{sticky: true}});
                poly.addTo(edgeLayer);
            }}
            for (var i=0; i<cycle.nodes.length; i++) {{
                var n = cycle.nodes[i];
                var marker = L.circleMarker([n[1], n[0]], {{
                    radius: 4, color: color, fillColor: color, fillOpacity: 0.6
                }});
                marker.bindTooltip("节点: " + n[2], {{sticky: true}});
                marker.addTo(nodeLayer);
            }}
            return {{edge: edgeLayer, node: nodeLayer}};
        }}

        function updateDisplay() {{
            var sortBy = document.getElementById('sortSelect').value;
            var sorted = [...cyclesData];
            if (sortBy === 'length') {{
                sorted.sort((a,b) => b.length_km - a.length_km);
            }} else if (sortBy === 'distance') {{
                sorted.sort((a,b) => a.min_dist_km - b.min_dist_km);
            }} else {{
                sorted.sort((a,b) => b.smoothness - a.smoothness);
            }}

            for (var key in currentLayers) {{
                if (currentLayers[key]) {{
                    map.removeLayer(currentLayers[key].edge);
                    map.removeLayer(currentLayers[key].node);
                }}
            }}
            currentLayers = {{}};

            var container = document.getElementById('checkboxes');
            container.innerHTML = '';

            for (var i=0; i<sorted.length; i++) {{
                var cycle = sorted[i];
                var color = getColor(i);
                var layers = createLayerGroup(cycle, color);
                var layerId = 'cycle_' + cycle.id;
                currentLayers[layerId] = layers;

                var label = document.createElement('label');
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = false;
                cb.addEventListener('change', (function(lyr) {{
                    return function(e) {{
                        if (e.target.checked) {{
                            map.addLayer(lyr.edge);
                            map.addLayer(lyr.node);
                        }} else {{
                            map.removeLayer(lyr.edge);
                            map.removeLayer(lyr.node);
                        }}
                    }};
                }})(layers));
                label.appendChild(cb);
                var text = `环${{cycle.id+1}} (长${{cycle.length_km.toFixed(2)}}km, 顺畅度${{cycle.smoothness}}, 距起点${{cycle.min_dist_km.toFixed(2)}}km)`;
                label.appendChild(document.createTextNode(text));
                container.appendChild(label);
            }}
        }}

        document.getElementById('sortSelect').addEventListener('change', updateDisplay);
        updateDisplay();
    </script>
</body>
</html>
    """

    # 修改：输出到 output/ 目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_html = os.path.join(OUTPUT_DIR, "cycles_map_final.html")
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ 地图已生成: {output_html}")

if __name__ == "__main__":
    main()
