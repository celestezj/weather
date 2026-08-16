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

---

> **隐私提示**：`config.json`、`ed25519-private.pem` 等含凭据的文件已在 `.gitignore` 中，**请勿提交或外传**。
> 可分享的只有空模板 `config.json.template`（含 `ed25519-private.pem.template`）。
