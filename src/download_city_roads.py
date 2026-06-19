#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OSM 道路数据预下载工具

从 OpenStreetMap 下载指定城市的道路数据，保存为 Shapefile 格式。
支持交互式输入城市名称，下载的道路类型与 build2.py 的 DEFAULT_BIKE_TYPES 保持一致。

用法：
    python src/download_city_roads.py

输出：
    ./data/城市名/城市名_roads.shp
"""

import os
import sys
import osmnx as ox
import geopandas as gpd
from shapely.geometry import LineString

# ==================== 与 build2.py 保持一致的自行车道路类型 ====================
DEFAULT_BIKE_TYPES = [
    'cycleway', 'path', 'track', 'bridleway', 'footway', 'pedestrian',
    'living_street', 'residential',
    'unclassified', 'service', 'tertiary', 'tertiary_link',
    'secondary', 'secondary_link', 'primary', 'primary_link',
    'road', 'unknown', 'bus_guideway'
]
# =============================================================================

def download_city_roads():
    """
    交互式下载指定城市的 OSM 道路数据，保存为 Shapefile。
    """
    print("=" * 60)
    print("🌍 OSM 道路数据预下载工具")
    print("=" * 60)
    print("此工具将从 OpenStreetMap 下载指定城市的道路数据")
    print("包含所有自行车可通行的道路类型")
    print("（与 build2.py 的 DEFAULT_BIKE_TYPES 保持一致）")
    print("-" * 60)

    # 1. 获取城市名称
    city = input("请输入城市名称（例如：Beijing, China）: ").strip()
    if not city:
        print("❌ 城市名称不能为空")
        return

    # 2. 获取输出目录
    city_name_clean = city.split(',')[0].strip()
    default_dir = f"./data/{city_name_clean}"
    output_dir = input(f"请输入输出文件夹（默认 {default_dir}）: ").strip()
    if not output_dir:
        output_dir = default_dir

    # 3. 确认下载
    print(f"\n📥 准备下载: {city}")
    print(f"   输出目录: {output_dir}")
    print(f"   道路类型: {len(DEFAULT_BIKE_TYPES)} 种")
    print("-" * 60)
    confirm = input("确认开始下载？(y/n，默认 y): ").strip().lower()
    if confirm and confirm != 'y':
        print("已取消下载。")
        return

    # 4. 构建 custom_filter（筛选所有自行车可通行道路）
    # 使用 network_type='all' 获取所有道路，再通过 custom_filter 筛选
    custom_filter = '["highway"]~["' + '"|"'.join(DEFAULT_BIKE_TYPES) + '"]'

    # 5. 执行下载
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n⏳ 正在从 OSM 下载 {city} 的道路数据...")
    print("   这可能需要数十分钟到数小时，取决于城市大小和网络速度。")

    try:
        G = ox.graph_from_place(
            city,
            network_type='all',
            custom_filter=custom_filter,
            simplify=True
        )

        # 提取边（道路）数据
        edges = ox.graph_to_gdfs(G, nodes=False, edges=True)

        # 精简字段，减小文件体积
        keep_cols = ['highway', 'name', 'length', 'geometry']
        for col in list(edges.columns):
            if col not in keep_cols:
                edges = edges.drop(columns=[col])

        # 保存为 Shapefile
        shp_path = os.path.join(output_dir, f"{city_name_clean}_roads.shp")
        edges.to_file(shp_path, driver='ESRI Shapefile')

        # 输出统计
        print("-" * 60)
        print(f"✅ 下载成功！")
        print(f"   文件路径: {shp_path}")
        print(f"   道路数量: {len(edges)} 条")
        print(f"   文件大小: {os.path.getsize(shp_path) / 1024 / 1024:.1f} MB")

        # 输出道路类型统计
        if 'highway' in edges.columns:
            highway_counts = edges['highway'].value_counts().head(10)
            print(f"\n   主要道路类型:")
            for hw, count in highway_counts.items():
                print(f"     - {hw}: {count} 条")

        print("\n" + "=" * 60)
        print("🎉 下一步")
        print("=" * 60)
        print(f"运行主程序处理数据：")
        print(f"  python src/build_road_network.py")
        print(f"  输入数据路径: {output_dir}")
        print("  裁剪范围可直接回车使用全量")
        print("=" * 60)

    except ox._errors.InsufficientResponseError:
        print("❌ 下载失败：该区域数据量过大，OSM 服务器返回了截断响应")
        print("   建议尝试更小的区域（如城市中心区），或使用 Geofabrik 下载")
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        print("\n可能的原因：")
        print("  - 城市名称格式不正确（请使用 '城市名, 国家' 格式）")
        print("  - 网络连接问题（访问 OSM 服务器可能需要代理）")
        print("  - 该城市在 OSM 中数据量过大，可尝试指定更小区域")
        print("  - 未安装 osmnx: pip install osmnx")


def main():
    """程序入口"""
    # 检查是否安装了 osmnx
    try:
        import osmnx
    except ImportError:
        print("❌ 未安装 osmnx，请先安装：")
        print("   pip install osmnx")
        sys.exit(1)

    download_city_roads()


if __name__ == "__main__":
    main()
