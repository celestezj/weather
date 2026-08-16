#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定位并查询和风天气（QWeather）。

定位逻辑复用 get_location.py（优先级：命令行 > config.json > IP 反查）。
鉴权支持两种方式（优先用 JWT）：
  1. JWT：用本地 Ed25519 私钥签发（和风官方推荐，按量计费，无免费额度）
  2. API Key：传统 key 参数（有免费额度，但官方说将逐步限制）

config.json：
{
  "latitude": null,
  "longitude": null,
  "qweather_host": "https://m453ig988p.re.qweatherapi.com",
  "qweather_key": "",                    // API Key 方式
  "qweather_kid": "凭据ID",              // JWT 方式：控制台 JWT 凭据 ID
  "qweather_sub": "项目ID",              // JWT 方式：控制台项目 ID
  "qweather_private_key": "ed25519-private.pem"   // 本地私钥路径
}

用法：
  python weather.py                     # 当前天气
  python weather.py --days 7            # 未来 7 天预报
  python weather.py --hours 24          # 未来 24 小时逐小时预报（含降雨量）
  python weather.py --json              # JSON 输出
  python weather.py --key YOUR_KEY      # 临时用 API Key（不写进配置）
  python weather.py --lat .. --lon ..   # 手动定位（复用定位优先级）
"""

import argparse
import base64
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import quote, urlencode

import get_location

API_HOST = "https://devapi.qweather.com"   # 免费订阅默认；可在 config.json 的 qweather_host 覆盖（如个性化域名）
GEO_HOST = "https://geoapi.qweather.com"
TIMEOUT = 8
JWT_TTL = 300   # JWT 有效期（秒），官方上限 86400

_WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class QWeatherError(Exception):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__("和风天气接口错误 code=%s %s" % (code, message or ""))


# ---------- JWT 鉴权 ----------

def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _der_tlv(data, offset):
    """解析 DER 的 TLV，返回 (tag, value, next_offset)。"""
    tag = data[offset]
    offset += 1
    length = data[offset]
    offset += 1
    if length & 0x80:
        num = length & 0x7f
        length = int.from_bytes(data[offset:offset + num], "big")
        offset += num
    return tag, data[offset:offset + length], offset + length


def _extract_ed25519_seed(path):
    """从 PKCS8 PEM 私钥中提取 Ed25519 的 32 字节种子。"""
    import base64
    pem = open(path, "rb").read()
    lines = [l.strip() for l in pem.split(b"\n") if l.strip() and not l.startswith(b"-----")]
    b64 = b"".join(lines)
    b64 += b"=" * (-len(b64) % 4)
    der = base64.b64decode(b64)
    tag, val, _ = _der_tlv(der, 0)
    if tag != 0x30:
        raise QWeatherError("sign", "私钥不是有效的 PKCS8 格式")
    off = 0
    _tag, _v, off = _der_tlv(val, off)
    _tag, alg, off = _der_tlv(val, off)
    if alg != b"\x06\x03\x2b\x65\x70":
        raise QWeatherError("sign", "私钥不是 Ed25519 算法")
    _tag, pk_val, _off = _der_tlv(val, off)
    _tag, seed, _ = _der_tlv(pk_val, 0)
    if len(seed) != 32:
        raise QWeatherError("sign", "Ed25519 种子长度异常: %d" % len(seed))
    return seed


def _sign_with_openssl(data_bytes, key_path):
    import subprocess
    proc = subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", key_path,
                           "-rawin", "-in", "-"], input=data_bytes, capture_output=True)
    if proc.returncode != 0:
        raise QWeatherError("sign", "openssl 签名失败: %s" %
                            proc.stderr.decode("utf-8", "replace"))
    return proc.stdout


def _sign_ed25519(data_bytes, key_path):
    """用 Ed25519 私钥签名：优先 PyNaCl，其次系统 openssl。"""
    try:
        from nacl.signing import SigningKey
    except ImportError:
        return _sign_with_openssl(data_bytes, key_path)
    seed = _extract_ed25519_seed(key_path)
    return SigningKey(seed).sign(data_bytes).signature


def make_jwt(kid, sub, private_key_path, ttl=JWT_TTL):
    """签发和风天气 JWT：header(kid) + payload(sub/iat/exp)，Ed25519 签名。"""
    header = {"alg": "EdDSA", "kid": kid}
    iat = int(time.time()) - 30   # 官方建议：iat 提前 30 秒，避免时钟误差
    payload = {"sub": sub, "iat": iat, "exp": iat + ttl}
    signing_input = _b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + \
                    _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url(_sign_ed25519(signing_input.encode("ascii"), private_key_path))
    return "%s.%s" % (signing_input, sig)


def build_auth(config, cli_key=None):
    """返回鉴权信息 dict（type=jwt 或 type=key），配置缺失时返回 None。"""
    kid = config.get("qweather_kid")
    sub = config.get("qweather_sub")
    priv_path = config.get("qweather_private_key")
    if kid and sub and priv_path:
        return {"type": "jwt", "token": make_jwt(kid, sub, priv_path)}
    key = cli_key or config.get("qweather_key")
    if key:
        return {"type": "key", "key": key}
    return None


# ---------- HTTP ----------

def fetch_json(req, timeout=TIMEOUT):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read()
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except Exception:
                pass
        raise QWeatherError(e.code, "HTTP %s %s" % (e.code, body.decode("utf-8", "replace")))


def _qweather_get(host, path, params, auth):
    params = dict(params)
    params.setdefault("lang", "zh")   # 强制中文文本，海外地点默认返回英文
    headers = {"User-Agent": "weather-locator/1.0", "Accept-Encoding": "gzip"}
    if auth["type"] == "jwt":
        headers["Authorization"] = "Bearer " + auth["token"]
    else:
        params["key"] = auth["key"]
    url = "%s%s?%s" % (host, path, urlencode(params))
    data = fetch_json(urllib.request.Request(url, headers=headers))
    if data.get("code") != "200":
        raise QWeatherError(data.get("code"), data.get("message"))
    return data


# ---------- 和风接口 ----------

def weather_now(lat, lon, auth, host=API_HOST):
    return _qweather_get(host, "/v7/weather/now",
                         {"location": "%.4f,%.4f" % (lon, lat)}, auth)


def weather_daily(lat, lon, auth, days, host=API_HOST):
    if days not in (3, 7):
        raise QWeatherError("days", "预报天数仅支持 3 或 7")
    return _qweather_get(host, "/v7/weather/%dd" % days,
                         {"location": "%.4f,%.4f" % (lon, lat)}, auth)


def weather_hourly(lat, lon, auth, hours, host=API_HOST):
    """逐小时预报（含每小时降水量 precip 和降水概率 pop）。"""
    if hours not in (24, 48):
        raise QWeatherError("hours", "小时预报仅支持 24 或 48")
    return _qweather_get(host, "/v7/weather/%dh" % hours,
                         {"location": "%.4f,%.4f" % (lon, lat)}, auth)


def city_lookup(lat, lon, auth):
    """经纬度反查地名，失败时返回 None（不影响天气查询）。"""
    try:
        data = _qweather_get(GEO_HOST, "/v2/city/lookup",
                             {"location": "%.4f,%.4f" % (lon, lat)}, auth)
        loc = (data.get("location") or [None])[0]
        if not loc:
            return None
        return {"name": loc.get("name"), "adm1": loc.get("adm1"), "country": loc.get("country")}
    except Exception:
        return None


# ---------- 地图链接 ----------

def build_map_url(config, lat, lon):
    """根据 config 的 map_providers 生成地图链接 URL（取列表第一个）。

    provider 支持：amap（高德，WGS84 自动纠偏）/ osm（OpenStreetMap）/ google（谷歌）。
    返回 {"provider": ..., "url": ...}，未配置或 provider 未知时返回 None。
    """
    providers = config.get("map_providers")
    if not providers:
        return None
    provider = str(providers[0]).lower()
    zoom = int(config.get("map_zoom", 16) or 16)
    name = config.get("map_name", "")
    lat_s = "%.4f" % lat
    lon_s = "%.4f" % lon
    if provider == "amap":
        url = "https://uri.amap.com/marker?position=%s,%s&coordinate=wgs84" % (lon_s, lat_s)
        if name:
            url += "&name=" + quote(name)
    elif provider == "osm":
        url = "https://www.openstreetmap.org/?mlat=%s&mlon=%s&zoom=%d" % (lat_s, lon_s, zoom)
    elif provider == "google":
        url = "https://www.google.com/maps?q=%s,%s&z=%d" % (lat_s, lon_s, zoom)
    else:
        return None
    return {"provider": provider, "url": url}


# ---------- 输出 ----------

def _place_str(result):
    place = result.get("place")
    if place:
        parts = [p for p in (place.get("country"), place.get("adm1"), place.get("name")) if p]
        if parts:
            return " ".join(parts)
    loc = result.get("location") or {}
    parts = [p for p in (loc.get("country"), loc.get("region"), loc.get("city")) if p]
    return " ".join(parts) if parts else "未知位置"


def _format_coord(loc):
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        return ""
    return "（%.4f, %.4f）" % (lat, lon)


def print_human(result):
    loc = result["location"]
    src = loc.get("source", "")
    now = result.get("now") or {}
    place = _place_str(result)
    print("地点: %s %s (定位方式: %s)" % (place, _format_coord(loc), src))
    if now:
        print("当前: %s %s℃（体感 %s℃）" % (now.get("text"), now.get("temp"), now.get("feelsLike")))
        wind = "%s%s级" % (now.get("windDir"), now.get("windScale"))
        print("天气: %s | 湿度 %s%% | 气压 %s hPa | 降水 %smm | 能见度 %skm" % (
            wind, now.get("humidity"), now.get("pressure"), now.get("precip"), now.get("vis")))
    update = result.get("updateTime") or (now.get("obsTime") if now else "")
    if update:
        print("更新时间: %s" % update)

    daily = result.get("forecast") or []
    if daily:
        print("\n未来%d天:" % len(daily))
        for d in daily:
            try:
                weekday = _WEEK[datetime.strptime(d["fxDate"], "%Y-%m-%d").weekday()]
            except (KeyError, ValueError):
                weekday = ""
            line = "%s %s: %s转%s %s℃/%s℃ %s" % (
                d.get("fxDate"), weekday, d.get("textDay"), d.get("textNight"),
                d.get("tempMax"), d.get("tempMin"), d.get("windDirDay"))
            print(line)

    hourly = result.get("hourly") or []
    if hourly:
        print("\n未来%d小时逐小时预报:" % len(hourly))
        for h in hourly:
            t = h.get("fxTime", "")
            if len(t) >= 16:
                t = t[11:16]
            print("%s  %s %s℃  | 降水 %smm  概率 %s%%" % (
                t, h.get("text"), h.get("temp"), h.get("precip"), h.get("pop")))


# ---------- 入口 ----------

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def collect(config, args):
    """定位并拉取天气数据，返回结果 dict。"""
    api_host = config.get("qweather_host") or API_HOST
    auth = build_auth(config, args.key)
    if auth is None:
        raise QWeatherError("auth", "未配置鉴权信息，请在 %s 中填写 API Key（qweather_key）"
                            "或 JWT（qweather_kid / qweather_sub / qweather_private_key）" % args.config)
    location = get_location.resolve_location(config, args.lat, args.lon)
    if location is None:
        raise QWeatherError("loc", "无法获取定位（手动配置无效且 IP 反查失败）")
    lat, lon = location["latitude"], location["longitude"]
    result = {"location": location, "place": city_lookup(lat, lon, auth)}
    map_info = build_map_url(config, lat, lon)
    if map_info:
        result["map"] = map_info
    if args.days:
        result["forecast"] = weather_daily(lat, lon, auth, args.days, api_host).get("daily", [])
    if args.hours:
        result["hourly"] = weather_hourly(lat, lon, auth, args.hours, api_host).get("hourly", [])
    now_data = weather_now(lat, lon, auth, api_host)
    result["now"] = now_data.get("now", {})
    result["updateTime"] = now_data.get("updateTime", "")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="定位并查询和风天气")
    parser.add_argument("--config", default="config.json", help="配置文件路径（默认 config.json）")
    parser.add_argument("--key", help="临时用 API Key（默认读配置）")
    parser.add_argument("--lat", type=float, help="手动指定纬度")
    parser.add_argument("--lon", type=float, help="手动指定经度")
    parser.add_argument("--days", type=int, default=0, help="预报天数：3 或 7，0 表示只看当前")
    parser.add_argument("--hours", type=int, default=0, help="逐小时预报：24 或 48，含每小时降水量")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--output", help="把 JSON 数据写入指定文件（供可视化读取）")
    parser.add_argument("--watch", type=int, default=0,
                        help="定时刷新：每隔 N 分钟重新拉取数据并重写 --output 文件")
    args = parser.parse_args(argv)

    config = get_location.load_config(args.config)
    if args.watch and not args.output:
        print("错误：--watch 需配合 --output 使用", file=sys.stderr)
        return 1

    if not args.watch:
        try:
            result = collect(config, args)
        except QWeatherError as e:
            print("错误：%s" % e, file=sys.stderr)
            return 1
        except Exception as e:
            print("错误：查询天气失败：%s" % e, file=sys.stderr)
            return 1

        if args.output:
            write_json(args.output, result)
            print("已写入 %s （%s）" % (args.output, result.get("updateTime", "")))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif not args.output:
            print_human(result)
        return 0

    # --watch 模式：先写一次，之后定时重写
    try:
        result = collect(config, args)
        write_json(args.output, result)
    except Exception as e:
        print("错误：%s" % e, file=sys.stderr)
        return 1
    print("已写入 %s，定时刷新开启：每 %d 分钟更新一次（Ctrl+C 停止）" % (args.output, args.watch))
    try:
        while True:
            time.sleep(args.watch * 60)
            try:
                result = collect(config, args)
                write_json(args.output, result)
                print("[%s] 已更新 %s" % (datetime.now().strftime("%H:%M:%S"), args.output))
            except Exception as e:
                print("[%s] 更新失败：%s" % (datetime.now().strftime("%H:%M:%S"), e), file=sys.stderr)
    except KeyboardInterrupt:
        print("\n已停止定时刷新")
        return 0


if __name__ == "__main__":
    sys.exit(main())
