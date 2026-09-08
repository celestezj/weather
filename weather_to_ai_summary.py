#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 weather_data.json 转换成 AI / 人更容易理解的自然语言摘要（默认写入 weather_summary.md）。

背景：原始 weather_data.json 中温度、降雨量(precip)、降雨概率(pop)都是字符串，
时间带 +08:00 时区后缀，未来24小时/7天降雨量也需要手动累加，AI 直接读容易算错。

本脚本做三件事：
  1. 把字符串数值统一转成数字，并标注单位（mm / % / ℃ / 级）；
  2. 把 ISO 时间统一成 "08-16 17:00" 格式并换算中国标准时间(UTC+8)可读形式；
  3. 预计算“未来24小时总降雨量”和“未来7天总降雨量”并生成要点摘要，
     让 AI 直接读汇总数字即可，不用自己累加。

用法：
  python weather_to_ai_summary.py                 # 读 weather_data.json，写 weather_summary.md
  python weather_to_ai_summary.py -i data.json    # 指定输入
  python weather_to_ai_summary.py -o out.md       # 指定输出

只依赖标准库，不影响 weather.py / run.ps1 / weather.html 的任何逻辑。
"""

import argparse
import json
import os
from datetime import datetime, timedelta

_WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def fnum(v, nd=2):
    """把字符串/数字安全转成数字；空值返回 0。"""
    if v is None or v == "":
        return 0
    try:
        return round(float(v) * 10 ** nd) / 10 ** nd
    except (TypeError, ValueError):
        return 0


def weekday(fxdate):
    """'YYYY-MM-DD' -> '周三'；解析失败返回空。"""
    try:
        return _WEEK[datetime.strptime(fxdate, "%Y-%m-%d").weekday()]
    except (KeyError, ValueError, TypeError):
        return ""


def fmt_dt(iso):
    """'2026-08-16T17:00+08:00' -> '2026-08-16 17:00 周日'；乱格式原样返回。"""
    s = iso or ""
    body = s[:16]
    if len(body) == 16:
        try:
            dt = datetime.strptime(body, "%Y-%m-%dT%H:%M")
            return "%s %s" % (body.replace("T", " "), weekday(dt.strftime("%Y-%m-%d")))
        except ValueError:
            pass
    return s
    # 说明：原始数据已带 +08:00 且素材本身即北京时间，无需再换算。


def rainy_hours(hourly):
    """hourly 中实际有降雨量>0的时段列表。"""
    return [h for h in hourly if fnum(h.get("precip")) > 0]


def gen_summary(data):
    """从 weather_data.json 生成自然语言摘要文本。"""
    loc = data.get("location") or {}
    place = data.get("place") or {}
    now = data.get("now") or {}
    hourly = data.get("hourly") or []
    daily = data.get("forecast") or []

    place_str = " ".join(filter(None, [
        place.get("country"), place.get("adm1"), place.get("name"),
        loc.get("region"), loc.get("city"),
    ])) or "未知位置"

    L = []
    L.append("# 天气数据摘要（供 AI 快速理解）")
    L.append("")
    L.append("- 地点：%s（纬度 %.4f，经度 %.4f，定位方式：%s）" % (
        place_str, fnum(loc.get("latitude")), fnum(loc.get("longitude")),
        loc.get("source", "")))
    L.append("- 数据更新时间：%s" % (data.get("updateTime") or now.get("obsTime") or "未知"))
    L.append("- 说明：以下单位统一为 毫米(mm)=降雨量，% = 降雨概率，℃ = 温度，级 = 风力等级。")
    L.append("")

    # ---- 当前天气 ----
    L.append("## 一、当前天气")
    L.append("")
    L.append("- 天气：%s；温度 %s℃；体感 %s℃" % (
        now.get("text", "—"), fnum(now.get("temp"), 1), fnum(now.get("feelsLike"), 1)))
    L.append("- 风：%s%s级；湿度 %s%%；气压 %s hPa；能见度 %s km；当前降水 %s mm" % (
        now.get("windDir", "—"), now.get("windScale", "—"),
        fnum(now.get("humidity")), fnum(now.get("pressure")), fnum(now.get("vis"), 1),
        fnum(now.get("precip"), 2)))
    L.append("")

    # ---- 未来24小时降雨要点 ----
    h_total = fnum(sum(fnum(h.get("precip")) for h in hourly), 2)
    rainy = rainy_hours(hourly)
    L.append("## 二、未来24小时降雨总量")
    L.append("")
    if hourly:
        span = "%s → %s" % (fmt_dt(hourly[0].get("fxTime")), fmt_dt(hourly[-1].get("fxTime")))
        L.append("- **未来24小时总降雨量：约 %s 毫米**（覆盖 %s，共 %d 个小时段）" % (
            h_total, span, len(hourly)))
        if rainy:
            peak = max(rainy, key=lambda h: fnum(h.get("precip")))
            L.append("- 有降雨的时段共 %d 个；最大单小时降雨 %s 毫米（%s，%s）" % (
                len(rainy), fnum(peak.get("precip")), fmt_dt(peak.get("fxTime")),
                peak.get("text", "—")))
        else:
            L.append("- 未来24小时内无降雨（所有时段降雨量为 0）。")
    else:
        L.append("- 无逐小时数据。")
    L.append("")

    # ---- 未来7天降雨要点 ----
    d_total = fnum(sum(fnum(d.get("precip")) for d in daily), 2)
    rainy_days = [d for d in daily if fnum(d.get("precip")) > 0]
    L.append("## 三、未来7天降雨总量")
    L.append("")
    if daily:
        L.append("- **未来7天总降雨量：约 %s 毫米**" % d_total)
        if rainy_days:
            top = max(rainy_days, key=lambda d: fnum(d.get("precip")))
            L.append("- 降雨主要集中在 %s（%s 毫米，%s）；本周其他天气以 %s/%s 为主" % (
                "%s(%s)" % (top.get("fxDate"), weekday(top.get("fxDate"))),
                fnum(top.get("precip")), top.get("textDay", "—"),
                daily[0].get("textDay", "—") if daily else "—",
                daily[0].get("textNight", "—") if daily else "—"))
        else:
            L.append("- 未来7天天气预报无降雨。")
        L.append("")
        L.append("| 日期 | 星期 | 天气 | 最高/最低温(℃) | 当日降雨(mm) | 风 |")
        L.append("|---|--|--|--|--|--|")
        for d in daily:
            wx = d.get("textDay") or d.get("textNight") or "—"
            night = d.get("textNight") or ""
            if night and night != d.get("textDay"):
                wx = "%s转%s" % (d.get("textDay"), night)
            L.append("| %s | %s | %s | %s / %s | **%s** | %s%s级 |" % (
                d.get("fxDate"), weekday(d.get("fxDate")), wx,
                fnum(d.get("tempMax"), 1), fnum(d.get("tempMin"), 1),
                fnum(d.get("precip")), d.get("windDirDay", "—"), d.get("windScaleDay", "—")))
    else:
        L.append("- 无7天预报数据。")
    L.append("")

    # ---- 未来24小时逐小时表 ----
    L.append("## 四、未来24小时逐小时明细")
    L.append("")
    if hourly:
        L.append("| 时间 | 天气 | 温度(℃) | 降水(mm) | 降水概率(%) | 风 |")
        L.append("|--|--|--|--|--|--|")
        for h in hourly:
            try:
                t = "%s %s" % (h.get("fxTime")[5:10], h.get("fxTime")[11:16])
            except (TypeError, IndexError):
                t = h.get("fxTime", "—")
            precip = fnum(h.get("precip"), 2)
            pp = fnum(h.get("pop"))
            rain_flag = "★" if precip > 0 else ""
            L.append("| %s | %s | %s | %s %s | %s | %s%s级 |" % (
                t, h.get("text", "—"), fnum(h.get("temp"), 1),
                precip, rain_flag, pp,
                h.get("windDir", "—"), h.get("windScale", "—")))
    else:
        L.append("- 无逐小时数据。")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="把 weather_data.json 转成 AI 更易读的摘要")
    ap.add_argument("-i", "--input", default="weather_data.json", help="输入 JSON（默认 weather_data.json）")
    ap.add_argument("-o", "--output", default="weather_summary.md", help="输出文件（默认 weather_summary.md）")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    out = gen_summary(data) + "\n"
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(out)
    print("已生成 %s （%s 字节）" % (args.output, os.path.getsize(args.output)))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())