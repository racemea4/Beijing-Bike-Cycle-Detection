#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
路网构建与简化工具
读取 OSM Shapefile 数据，构建路网图并执行简化，输出 GraphML 和 HTML 地图。
"""

import os
import glob
import re
import warnings
import geopandas as gpd
import networkx as nx
import pandas as pd
import numpy as np
from shapely.geometry import LineString, MultiLineString, Point
import folium
from folium import plugins

warnings.filterwarnings("ignore")

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
    print("提示: 未安装 tqdm，进度条将不显示。可通过 'pip install tqdm' 安装。")

# ======================= 原始图构建器 =======================
class OSMGraphBuilder:
    DEFAULT_BIKE_TYPES = [
        'cycleway', 'path', 'track', 'bridleway', 'footway', 'pedestrian',
        'living_street', 'residential',
        'unclassified', 'service', 'tertiary', 'tertiary_link',
        'secondary', 'secondary_link', 'primary', 'primary_link',
        'road', 'unknown', 'bus_guideway'
    ]

    def __init__(self, data_folder, output_dir, bike_types=None, bbox=None):
        self.data_folder = os.path.abspath(data_folder)
        self.output_dir = os.path.abspath(output_dir)
        self.bike_types = bike_types or self.DEFAULT_BIKE_TYPES
        self.bbox = bbox
        os.makedirs(self.output_dir, exist_ok=True)
        self.signals_shp_path = None

    def find_road_layers(self):
        shp_files = glob.glob(os.path.join(self.data_folder, "**", "*.shp"), recursive=True)
        road_layers = []
        for shp_path in shp_files:
            filename = os.path.basename(shp_path).lower()
            try:
                gdf = gpd.read_file(shp_path)
                geom_types = set(gdf.geometry.geom_type.unique())
                if not (geom_types.issubset({'LineString', 'MultiLineString'})):
                    continue
                if 'roads' in filename:
                    print(f"✓ 找到道路图层: {shp_path}")
                    road_layers.append(gdf)
                elif 'fclass' in gdf.columns and gdf['fclass'].notna().any():
                    unique_fclass = set(gdf['fclass'].dropna().unique())
                    if any(t in unique_fclass for t in ['motorway', 'primary', 'residential', 'cycleway']):
                        print(f"✓ 通过字段识别道路图层: {shp_path}")
                        road_layers.append(gdf)
            except Exception as e:
                print(f"✗ 读取失败 {shp_path}: {e}")
        return road_layers

    def merge_road_layers(self, layers):
        if not layers:
            return None
        for i, gdf in enumerate(layers):
            if gdf.crs is None:
                layers[i] = gdf.set_crs("EPSG:4326")
            elif gdf.crs.to_string() != "EPSG:4326":
                layers[i] = gdf.to_crs("EPSG:4326")
        return pd.concat(layers, ignore_index=True)

    def filter_bike_network(self, roads_gdf):
        if 'fclass' in roads_gdf.columns:
            type_field = 'fclass'
        elif 'highway' in roads_gdf.columns:
            type_field = 'highway'
        else:
            raise ValueError("找不到道路类型字段")
        condition = roads_gdf[type_field].isin(self.bike_types)
        if 'bicycle' in roads_gdf.columns:
            condition |= (roads_gdf['bicycle'] == 'yes')
            condition &= (roads_gdf['bicycle'] != 'no')
        bike_network = roads_gdf[condition].copy()
        print(f"筛选后自行车道数量: {len(bike_network)}")
        return bike_network

    def clip_by_bbox(self, gdf):
        if self.bbox is None:
            return gdf
        min_lon, min_lat, max_lon, max_lat = self.bbox
        clipped = gdf.cx[min_lon:max_lon, min_lat:max_lat].copy()
        print(f"裁剪后剩余要素数: {len(clipped)}")
        return clipped

    def load_traffic_signals(self):
        shp_files = glob.glob(os.path.join(self.data_folder, "**", "*.shp"), recursive=True)
        for shp_path in shp_files:
            filename = os.path.basename(shp_path).lower()
            if 'traffic' in filename and filename.endswith('.shp'):
                try:
                    gdf = gpd.read_file(shp_path)
                    if set(gdf.geometry.geom_type.unique()) != {'Point'}:
                        continue
                    if 'fclass' in gdf.columns:
                        signals = gdf[gdf['fclass'] == 'traffic_signals'].copy()
                        if not signals.empty:
                            print(f"✓ 红绿灯数据读取自: {shp_path}，共 {len(signals)} 个点")
                            if self.bbox:
                                signals = self.clip_by_bbox(signals)
                                print(f"   裁剪后红绿灯数量: {len(signals)}")
                            self.signals_shp_path = shp_path
                            return signals
                except:
                    pass
        print("⚠ 未找到红绿灯数据")
        self.signals_shp_path = None
        return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

    def build_graph(self, bike_network):
        G = nx.Graph()
        total_rows = len(bike_network)
        iterator = tqdm(bike_network.iterrows(), total=total_rows, desc="构建图") if tqdm else bike_network.iterrows()
        for _, row in iterator:
            geom = row.geometry
            if isinstance(geom, LineString):
                coords = list(geom.coords)
                for i in range(len(coords)-1):
                    u = coords[i]
                    v = coords[i+1]
                    G.add_edge(u, v, weight=row.geometry.length)
            elif isinstance(geom, MultiLineString):
                for line in geom.geoms:
                    coords = list(line.coords)
                    for i in range(len(coords)-1):
                        u = coords[i]
                        v = coords[i+1]
                        G.add_edge(u, v, weight=line.length)
        for node in G.nodes:
            G.nodes[node]['x'] = node[0]
            G.nodes[node]['y'] = node[1]
        print(f"图构建完成: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")
        return G

    def save_graph(self, graph, filename="original_bike_graph.graphml"):
        path = os.path.join(self.output_dir, filename)
        nx.write_graphml(graph, path)
        print(f"原始图已保存: {path}")
        return path

    def run(self):
        print("="*60)
        print("Step 1: 构建原始路网图")
        print(f"数据文件夹: {self.data_folder}")
        print(f"输出目录: {self.output_dir}")
        if self.bbox:
            print(f"裁剪范围: {self.bbox}")
        else:
            print("裁剪范围: 全量")
        road_layers = self.find_road_layers()
        if not road_layers:
            raise RuntimeError("未找到道路图层")
        roads_gdf = self.merge_road_layers(road_layers)
        bike_network = self.filter_bike_network(roads_gdf)
        if self.bbox:
            bike_network = self.clip_by_bbox(bike_network)
        signals = self.load_traffic_signals()
        graph = self.build_graph(bike_network)
        graph_path = self.save_graph(graph)
        return graph_path, self.signals_shp_path


# ======================= 路网简化器 =======================
class GraphSimplifier:
    def __init__(self, input_graphml, signals_shp=None, output_dir="./output_simplified", bbox=None):
        self.input_graphml = input_graphml
        self.signals_shp = signals_shp
        self.output_dir = os.path.abspath(output_dir)
        self.bbox = bbox
        os.makedirs(self.output_dir, exist_ok=True)
        self.G = None

    def load_graph(self):
        print("加载原始图...")
        self.G = nx.read_graphml(self.input_graphml)
        nodes = list(self.G.nodes)
        if tqdm:
            for node in tqdm(nodes, desc="解析节点坐标"):
                data = self.G.nodes[node]
                if 'x' not in data or 'y' not in data:
                    coords = node.strip('()').split(', ')
                    data['x'] = float(coords[0])
                    data['y'] = float(coords[1])
        else:
            for node in nodes:
                data = self.G.nodes[node]
                if 'x' not in data or 'y' not in data:
                    coords = node.strip('()').split(', ')
                    data['x'] = float(coords[0])
                    data['y'] = float(coords[1])
        print(f"原始图: {self.G.number_of_nodes()} 节点, {self.G.number_of_edges()} 边")

    def clip_by_bbox(self):
        if self.bbox is None:
            return
        min_lon, min_lat, max_lon, max_lat = self.bbox
        print("裁剪子图...")
        keep = [n for n, d in self.G.nodes(data=True) if min_lon<=d['x']<=max_lon and min_lat<=d['y']<=max_lat]
        self.G = self.G.subgraph(keep).copy()
        print(f"裁剪后: {self.G.number_of_nodes()} 节点, {self.G.number_of_edges()} 边")

    def match_traffic_signals(self):
        if not self.signals_shp or not os.path.exists(self.signals_shp):
            print("未提供红绿灯文件，跳过标记")
            for n in self.G.nodes:
                self.G.nodes[n]['has_traffic_light'] = False
            return
        print("匹配红绿灯节点...")
        signals = gpd.read_file(self.signals_shp)
        if 'fclass' in signals.columns:
            signals = signals[signals['fclass'] == 'traffic_signals']
        elif 'highway' in signals.columns:
            signals = signals[signals['highway'] == 'traffic_signals']
        else:
            print("无法识别红绿灯字段，跳过标记")
            for n in self.G.nodes:
                self.G.nodes[n]['has_traffic_light'] = False
            return
        if signals.crs is None:
            signals.set_crs("EPSG:4326", inplace=True)
        elif signals.crs.to_string() != "EPSG:4326":
            signals = signals.to_crs("EPSG:4326")
        signal_set = {(round(geom.x,7), round(geom.y,7)) for geom in signals.geometry}
        nodes = list(self.G.nodes)
        if tqdm:
            for node in tqdm(nodes, desc="标记红绿灯"):
                data = self.G.nodes[node]
                lon = round(data['x'],7)
                lat = round(data['y'],7)
                data['has_traffic_light'] = (lon, lat) in signal_set
        else:
            for node in nodes:
                data = self.G.nodes[node]
                lon = round(data['x'],7)
                lat = round(data['y'],7)
                data['has_traffic_light'] = (lon, lat) in signal_set
        cnt = sum(1 for n in self.G.nodes if self.G.nodes[n].get('has_traffic_light', False))
        print(f"匹配到红绿灯节点: {cnt}")

    def project_to_meters(self):
        print("投影到米制坐标系...")
        nodes = list(self.G.nodes)
        nodes_gdf = gpd.GeoDataFrame(
            {'node': nodes},
            geometry=[Point(self.G.nodes[n]['x'], self.G.nodes[n]['y']) for n in nodes],
            crs="EPSG:4326"
        )
        nodes_proj = nodes_gdf.to_crs("EPSG:3857")
        for idx, row in nodes_proj.iterrows():
            node = row['node']
            self.G.nodes[node]['x_proj'] = row.geometry.x
            self.G.nodes[node]['y_proj'] = row.geometry.y
        edges = list(self.G.edges(data=True))
        if tqdm:
            for u, v, data in tqdm(edges, desc="计算边长度（米）"):
                x1 = self.G.nodes[u]['x_proj']
                y1 = self.G.nodes[u]['y_proj']
                x2 = self.G.nodes[v]['x_proj']
                y2 = self.G.nodes[v]['y_proj']
                data['len_m'] = np.hypot(x2-x1, y2-y1)
        else:
            for u, v, data in edges:
                x1 = self.G.nodes[u]['x_proj']
                y1 = self.G.nodes[u]['y_proj']
                x2 = self.G.nodes[v]['x_proj']
                y2 = self.G.nodes[v]['y_proj']
                data['len_m'] = np.hypot(x2-x1, y2-y1)
        print("投影完成")

    def cluster_by_short_edges(self, threshold=30):
        print("构建短边图...")
        H = nx.Graph()
        edges_list = list(self.G.edges(data=True))
        if tqdm:
            for u, v, data in tqdm(edges_list, desc="添加短边"):
                if data.get('len_m', 0) < threshold:
                    H.add_edge(u, v)
        else:
            for u, v, data in edges_list:
                if data.get('len_m', 0) < threshold:
                    H.add_edge(u, v)
        for n in self.G.nodes:
            H.add_node(n)

        print("计算连通分量...")
        comps = list(nx.connected_components(H))
        num = len(comps)
        print(f"短边连通簇数量: {num}")

        print("合并簇节点...")
        cluster_to_nodes = {}
        for idx, comp in enumerate(comps):
            for node in comp:
                cluster_to_nodes.setdefault(idx, []).append(node)

        new_node_map = {}
        new_nodes = []
        iterator = tqdm(cluster_to_nodes.items(), desc="合并簇") if tqdm else cluster_to_nodes.items()
        for cid, nodes_in in iterator:
            xs = [self.G.nodes[n]['x_proj'] for n in nodes_in]
            ys = [self.G.nodes[n]['y_proj'] for n in nodes_in]
            cx = np.mean(xs)
            cy = np.mean(ys)
            has_sig = any(self.G.nodes[n].get('has_traffic_light', False) for n in nodes_in)
            new_id = f"c{cid}"
            for n in nodes_in:
                new_node_map[n] = new_id
            new_nodes.append((new_id, cx, cy, has_sig))

        G2 = nx.Graph()
        for nid, cx, cy, hs in new_nodes:
            G2.add_node(nid, x_proj=cx, y_proj=cy, has_traffic_light=hs)

        print("添加边...")
        edges_added = set()
        edge_list = list(self.G.edges())
        iterator2 = tqdm(edge_list, desc="添加边") if tqdm else edge_list
        for u, v in iterator2:
            cu = new_node_map[u]
            cv = new_node_map[v]
            if cu == cv:
                continue
            if (cu, cv) not in edges_added:
                edges_added.add((cu, cv))
                x1 = G2.nodes[cu]['x_proj']
                y1 = G2.nodes[cu]['y_proj']
                x2 = G2.nodes[cv]['x_proj']
                y2 = G2.nodes[cv]['y_proj']
                dist = np.hypot(x2 - x1, y2 - y1)
                G2.add_edge(cu, cv, len_m=dist)

        self.G = G2
        print(f"聚类后: {self.G.number_of_nodes()} 节点, {self.G.number_of_edges()} 边")

    def simplify_degree2_non_signal(self):
        G = self.G.to_undirected()
        to_remove = [n for n, deg in G.degree() if deg == 2 and not G.nodes[n].get('has_traffic_light', False)]
        print(f"待简化度2节点数: {len(to_remove)}")
        iterator = tqdm(to_remove, desc="简化度2节点") if tqdm else to_remove
        for node in iterator:
            if node not in G:
                continue
            nb = list(G.neighbors(node))
            if len(nb) != 2:
                continue
            u, v = nb
            len1 = G[u][node].get('len_m', 0)
            len2 = G[node][v].get('len_m', 0)
            new_len = len1 + len2
            if G.has_edge(u, v):
                old_len = G[u][v].get('len_m', float('inf'))
                new_len = min(old_len, new_len)
            G.add_edge(u, v, len_m=new_len)
            G.remove_node(node)
        G.remove_nodes_from(list(nx.isolates(G)))
        self.G = G
        print(f"简化后: {self.G.number_of_nodes()} 节点, {self.G.number_of_edges()} 边")

    def prune_leaves(self):
        changed = True
        while changed:
            changed = False
            leaves = [n for n, deg in self.G.degree() if deg <= 1]
            if leaves:
                self.G.remove_nodes_from(leaves)
                changed = True
        print(f"剪枝后: {self.G.number_of_nodes()} 节点, {self.G.number_of_edges()} 边")

    def reproject_to_wgs84(self):
        print("反投影回 WGS84...")
        nodes = list(self.G.nodes)
        nodes_gdf = gpd.GeoDataFrame(
            {'node': nodes},
            geometry=[Point(self.G.nodes[n]['x_proj'], self.G.nodes[n]['y_proj']) for n in nodes],
            crs="EPSG:3857"
        )
        nodes_gdf = nodes_gdf.to_crs("EPSG:4326")
        for idx, row in nodes_gdf.iterrows():
            nid = row['node']
            self.G.nodes[nid]['x'] = row.geometry.x
            self.G.nodes[nid]['y'] = row.geometry.y
        print("反投影完成")

    def save_graph(self, filename="final_simplified.graphml"):
        path = os.path.join(self.output_dir, filename)
        for n, d in self.G.nodes(data=True):
            for key in ['geometry', 'x_proj', 'y_proj']:
                d.pop(key, None)
        for u, v, d in self.G.edges(data=True):
            d.pop('geometry', None)
        nx.write_graphml(self.G, path)
        print(f"简化图已保存: {path}")
        return path

    def save_map(self, filename="final_simplified_map.html"):
        """强制生成地图，添加进度条"""
        n_nodes = self.G.number_of_nodes()
    
        # 空图保护
        if n_nodes == 0:
            print("⚠️ 图中没有节点，跳过地图生成（裁剪范围内可能没有道路数据）")
            print("   提示：请扩大裁剪范围，或检查输入数据是否包含该区域的道路")
            return None
    
        print(f"正在生成 HTML 地图（节点数: {n_nodes}），请耐心等待...")
        coords = np.array([(d['x'], d['y']) for _, d in self.G.nodes(data=True)])
        center = (coords[:,0].mean(), coords[:,1].mean())
        m = folium.Map(location=[center[1], center[0]], zoom_start=12, tiles='Cartodb Positron')

        edges = list(self.G.edges())
        print("  添加边...")
        if tqdm:
            for u, v in tqdm(edges, desc="边"):
                x1, y1 = self.G.nodes[u]['x'], self.G.nodes[u]['y']
                x2, y2 = self.G.nodes[v]['x'], self.G.nodes[v]['y']
                folium.PolyLine([(y1, x1), (y2, x2)], color='gray', weight=1.5, opacity=0.6).add_to(m)
        else:
            for u, v in edges:
                x1, y1 = self.G.nodes[u]['x'], self.G.nodes[u]['y']
                x2, y2 = self.G.nodes[v]['x'], self.G.nodes[v]['y']
                folium.PolyLine([(y1, x1), (y2, x2)], color='gray', weight=1.5, opacity=0.6).add_to(m)

        nodes = list(self.G.nodes(data=True))
        print("  添加节点...")
        if tqdm:
            for node, d in tqdm(nodes, desc="节点"):
                color = 'red' if d.get('has_traffic_light', False) else 'gray'
                folium.CircleMarker([d['y'], d['x']], radius=3, color=color, fill=True, fill_opacity=0.8).add_to(m)
        else:
            for node, d in nodes:
                color = 'red' if d.get('has_traffic_light', False) else 'gray'
                folium.CircleMarker([d['y'], d['x']], radius=3, color=color, fill=True, fill_opacity=0.8).add_to(m)

        plugins.Fullscreen().add_to(m)
        path = os.path.join(self.output_dir, filename)
        m.save(path)
        print(f"节点-边地图已保存: {path}")
        return path

    def run(self):
        print("\n" + "="*60)
        print("Step 2: 简化路网图（聚类 -> 简化度2 -> 剪枝）")
        self.load_graph()
        if self.bbox:
            self.clip_by_bbox()
        self.match_traffic_signals()
        self.project_to_meters()
        self.cluster_by_short_edges(threshold=30)
        self.simplify_degree2_non_signal()
        self.prune_leaves()
        self.reproject_to_wgs84()
        graph_out = self.save_graph()
        map_out = self.save_map()
        return graph_out, map_out


# ======================= 辅助函数 =======================
def parse_coordinate(s):
    s = s.strip()
    if not s:
        return None
    match = re.search(r'-?\d+\.?\d*', s)
    if match:
        return float(match.group())
    raise ValueError("无效数字")

def get_coordinate_input(prompt, default=None):
    while True:
        inp = input(prompt).strip()
        if not inp and default is not None:
            return default
        try:
            return parse_coordinate(inp)
        except ValueError:
            print("❌ 输入无效，请输入数字（如 116.20）")


def get_data_bounds(data_folder):
    temp = OSMGraphBuilder(data_folder, output_dir="./temp_ignore")
    road_layers = temp.find_road_layers()
    if not road_layers:
        return None
    merged = temp.merge_road_layers(road_layers)
    if merged is None or merged.empty:
        return None
    return merged.total_bounds


# ======================= 主程序 =======================
def main():
    print("=" * 60)
    print("一站式路网构建与简化工具")
    print("=" * 60)

    data_folder = input("请输入数据文件夹路径（包含 .shp 文件）: ").strip()
    if not os.path.exists(data_folder):
        print("❌ 路径不存在")
        return

    bounds = get_data_bounds(data_folder)
    if bounds is not None:
        min_lon, min_lat, max_lon, max_lat = bounds
        print(f"\n📐 数据总体范围：经度 {min_lon:.6f} ~ {max_lon:.6f}，纬度 {min_lat:.6f} ~ {max_lat:.6f}")
    else:
        min_lon = min_lat = max_lon = max_lat = None
        print("⚠ 无法自动获取数据总体范围")

    print("\n请输入裁剪范围（可直接回车使用全量数据）")
    if min_lon is not None:
        west = get_coordinate_input(f"经度最小值（默认 {min_lon:.6f}）: ", default=min_lon)
        east = get_coordinate_input(f"经度最大值（默认 {max_lon:.6f}）: ", default=max_lon)
        south = get_coordinate_input(f"纬度最小值（默认 {min_lat:.6f}）: ", default=min_lat)
        north = get_coordinate_input(f"纬度最大值（默认 {max_lat:.6f}）: ", default=max_lat)
    else:
        west = get_coordinate_input("经度最小值: ")
        east = get_coordinate_input("经度最大值: ")
        south = get_coordinate_input("纬度最小值: ")
        north = get_coordinate_input("纬度最大值: ")
    bbox = (west, south, east, north)

    # 修改：默认输出目录改为 "output"（与 README 一致）
    default_out = os.path.join(os.getcwd(), "output")
    output_dir = input(f"请输入输出目录（默认 {default_out}）: ").strip()
    if not output_dir:
        output_dir = default_out
    output_dir = os.path.abspath(output_dir)

    builder = OSMGraphBuilder(data_folder, output_dir, bbox=bbox)
    original_graph_path, signals_shp_path = builder.run()
    print("原始图构建完成，准备简化...")

    if signals_shp_path:
        print(f"使用红绿灯文件: {signals_shp_path}")
    else:
        print("未找到红绿灯文件，简化时将跳过红绿灯标记")

    simplifier = GraphSimplifier(original_graph_path, signals_shp_path, output_dir, bbox=bbox)
    final_graph, final_map = simplifier.run()

    print("\n" + "=" * 60)
    print("🎉 全部完成！")
    print(f"输出目录: {output_dir}")
    print(f"最终简化图: {final_graph}")
    print(f"最终 HTML 地图: {final_map}")
    print("提示：如果 HTML 地图过大导致浏览器卡顿，建议使用 QGIS 查看 .graphml 文件。")


if __name__ == "__main__":
    main()
