# 天气工具 · 首次使用说明

面向新用户：装好 Python 后，按下面几步配置，之后双击即可启动。

## 1. 前置条件

- 已有 **Python 3.6+** 或者 **Anaconda**（未装请先安装）。

## 2. 安装依赖

执行 **`install.bat`**，自动检测 Python、安装依赖；默认源失败会自动切阿里云镜像。
或手动执行：

```bash
python -m pip install -r requirements.txt
```

## 3. 配置和风天气凭据

去 [和风天气](https://dev.qweather.com) 注册并创建项目。两种鉴权方式任选其一。

### 方式 A：API Key（更简单）

1. 在和风控制台创建一个 API Key。
2. 把 `config.json.template` 复制一份，改名为 **`config.json`**，填入：
   - `qweather_key`：你的 API Key
   - `qweather_host`：可留空（默认用 `https://devapi.qweather.com`）

### 方式 B：JWT（官方推荐，更安全）

1. 生成本地 Ed25519 密钥对（PKCS8 格式）：
   ```bash
   openssl genpkey -algorithm ED25519 -out ed25519-private.pem
   openssl pkey -pubout -in ed25519-private.pem > ed25519-public.pem
   ```
2. 在和风控制台上传公钥 `ed25519-public.pem`，创建 JWT 凭据，拿到 **kid**、**sub** 和**个性化 Host**。
3. 复制 `config.json.template` 为 **`config.json`**，填入：

   | 字段 | 说明 |
   |---|---|
   | `qweather_host` | 控制台给你的个性化 Host（必填，JWT 凭据绑定它） |
   | `qweather_kid` | JWT 凭据 ID（kid） |
   | `qweather_sub` | JWT 项目 ID（sub，**不是**开发者 ID） |
   | `qweather_private_key` | 私钥文件名，如 `ed25519-private.pem` |

## 4. 配置位置（可选）

- **自动定位**：`latitude` / `longitude` 填写 `null`，启动时会按 IP 反查。
- **固定位置**：填入经纬度（如 `31.24` / `121.40`），网页坐标可点击打开地图。

## 5. 启动

执行 **`quick_start.bat`**，会自动完成：
1. 拉取天气数据（`weather.py` 每 30 分钟刷新一次，可以在 run.ps1 中修改间隔时间）；
2. 启动本地服务（端口 **8055**）；
3. 打开浏览器访问 `http://localhost:8055/weather.html`。

关闭启动窗口即停止。以后每次使用只需双击 `quick_start.bat`。

## 6. 仅一次性生成 weather_data.json（不起服务）

如果只想一次性拉取数据并生成 `weather_data.json`（跑完即退出，不启动 HTTP 服务、
不常驻刷新），直接执行：

```bash
python weather.py --days 7 --hours 24 --output weather_data.json
```

这与 `quick_start.bat` 用的是同一套参数，只是去掉了 `--watch 30`；数据结构和网页读取的
完全一致。需要手动重新生成数据（例如更新坐标或手动刷新）时用这条即可。

## 7. 生成 AI 易读的天气摘要（可选）

`weather_data.json` 里的温度、降雨量等是字符串，时间带时区后缀，且未来24小时/7天
降雨量需要手动累加，AI 直接读容易算错。可用脚本转成 AI 更易读的摘要：

```bash
python weather_to_ai_summary.py
```

- 读取 `weather_data.json`，生成 **`weather_summary.md`**；
- 把字符串数值统一转成数字并标注单位（mm / % / ℃ / 级）；
- **预计算**「未来24小时总降雨量」和「未来7天总降雨量」并汇总要点，AI 直接读数字即可，
  不用自己累加；
- 含逐小时明细、每日常温/降雨表，有降雨的时段会标 `★`。

自定义输入/输出：

```bash
python weather_to_ai_summary.py -i xxx.json -o out.md
```

`weather_data.json` 每次更新后重跑一次即可。该脚本独立运行，不影响原有的
`quick_start.bat` 启动方式和网页展示。

## 8. 作为 Claude Code 技能使用（可选）

本项目已打包成 Claude Code 技能，可直接拷到你的技能目录全局使用：

- 源码位置：`.claude/skills/qweather/`
- **全局安装**：把整个 `qweather` 文件夹复制到用户技能目录（Windows 路径）：
  ```
  %USERPROFILE%\.claude\skills\qweather\
  ```
- 技能内自包含：`SKILL.md`（触发说明）+ `scripts/`（`weather.py`、`get_location.py`、
  `weather_to_ai_summary.py`）+ `fetch.sh`（一键拉取并生成摘要）+ 空模板。不含任何凭据。

技能默认**不起 http 服务**，直接用 `run.ps1` / `quick_start.bat` 的原有方式不受影响。
在 Claude Code 里触发 `qweather` 技能后，它会告知怎么生成 `weather_data.json` 和
`weather_summary.md`。

> 注意：技能里的 `scripts/*.py` 是当前版本的**快照**。若你之后改了仓库里的脚本，
> 需重新拷入 `.claude/skills/qweather/scripts/` 保持同步。

---

> **隐私提示**：`config.json`、`ed25519-private.pem` 等含凭据的文件已在 `.gitignore` 中，**请勿提交或外传**。
> 可分享的只有空模板 `config.json.template`（含 `ed25519-private.pem.template`）。
