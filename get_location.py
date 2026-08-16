#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取定位经纬度。

优先级（从高到低）：
  1. 命令行参数 --lat / --lon（两个一起给才生效）
  2. 配置文件 config.json 中的 latitude / longitude
  3. 通过公网 IP 反查定位（ip-api.com 失败时自动尝试 ipapi.co）

用法：
  python get_location.py                    # 自动：手动配置 > IP 反查
  python get_location.py --json             # 以 JSON 格式输出
  python get_location.py --config other.json
  python get_location.py --lat 31.24 --lon 121.40   # 临时手动指定

config.json 格式（字段可留空、省略或写 null，不填则忽略）：
{
  "latitude": 31.24,
  "longitude": 121.40
}
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# (名称, 接口地址)，依次尝试
IP_PROVIDERS = [
    ("ip-api", "http://ip-api.com/json/"),
    ("ipapi.co", "https://ipapi.co/json/"),
]

TIMEOUT = 8  # 秒


def load_config(path):
    """读取配置文件，不存在或内容非法时返回空 dict。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (IOError, ValueError):
        return {}


def validate_coord(value, kind):
    """校验经纬度数值，合法返回 float，否则返回 None。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if kind == "lat" and not -90.0 <= v <= 90.0:
        return None
    if kind == "lon" and not -180.0 <= v <= 180.0:
        return None
    return v


def ip_lookup():
    """通过公网 IP 反查定位，成功返回 dict，全部失败返回 None。"""
    for name, url in IP_PROVIDERS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "weather-locator/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            result = _parse_ip_result(name, data)
            if result:
                return result
        except Exception:
            continue
    return None


def _parse_ip_result(provider, data):
    if provider == "ip-api" and data.get("status") != "success":
        return None
    if provider == "ipapi.co" and data.get("error") is not None:
        return None
    # 各接口字段名不同：ip-api 用 lat/lon/regionName，ipapi.co 用 latitude/longitude/region
    lat = validate_coord(data.get("latitude", data.get("lat")), "lat")
    lon = validate_coord(data.get("longitude", data.get("lon")), "lon")
    if lat is None or lon is None:
        return None
    region = data.get("regionName") or data.get("region")
    return {
        "source": "ip_lookup",
        "provider": provider,
        "latitude": lat,
        "longitude": lon,
        "city": data.get("city"),
        "region": region,
        "country": data.get("country_name") or data.get("countryName") or data.get("country"),
    }


def _print_human(loc):
    if loc["source"] == "manual_cli":
        src = "命令行参数手动指定"
    elif loc["source"] == "manual_config":
        src = "配置文件手动指定"
    else:
        src = "IP 反查（%s）" % loc["provider"]
    print("定位方式: %s" % src)
    print("纬度: %s" % loc["latitude"])
    print("经度: %s" % loc["longitude"])
    parts = [p for p in (loc["country"], loc["region"], loc["city"]) if p]
    if parts:
        print("位置: %s" % " ".join(parts))


def resolve_location(config, cli_lat, cli_lon):
    """按优先级解析定位：CLI 手动 > 配置文件手动 > IP 反查。

    返回 location dict 或 None。CLI 只传一个参数时打印警告并忽略。
    """
    cli_lat = validate_coord(cli_lat, "lat")
    cli_lon = validate_coord(cli_lon, "lon")
    cfg_lat = validate_coord(config.get("latitude"), "lat")
    cfg_lon = validate_coord(config.get("longitude"), "lon")

    if (cli_lat is None) != (cli_lon is None):
        print("警告：--lat 与 --lon 需同时指定才生效，已忽略命令行手动指定", file=sys.stderr)
    elif cli_lat is not None and cli_lon is not None:
        return {"source": "manual_cli", "provider": None, "latitude": cli_lat,
                "longitude": cli_lon, "city": None, "region": None, "country": None}
    elif cfg_lat is not None and cfg_lon is not None:
        return {"source": "manual_config", "provider": None, "latitude": cfg_lat,
                "longitude": cfg_lon, "city": None, "region": None, "country": None}
    return ip_lookup()


def main(argv=None):
    parser = argparse.ArgumentParser(description="获取定位经纬度")
    parser.add_argument("--config", default="config.json", help="配置文件路径（默认 config.json）")
    parser.add_argument("--lat", type=float, help="手动指定纬度")
    parser.add_argument("--lon", type=float, help="手动指定经度")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    location = resolve_location(config, args.lat, args.lon)

    if location is None:
        print("错误：无法获取定位（手动配置无效且 IP 反查失败）", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(location, ensure_ascii=False, indent=2))
    else:
        _print_human(location)
    return 0


if __name__ == "__main__":
    sys.exit(main())
