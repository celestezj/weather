[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host '============================================'
Write-Host '  天气工具 - 依赖一键安装'
Write-Host '============================================'
Write-Host ''

# 1. 检查 python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host '[错误] 未检测到 python，请先安装 Python 3.6+ 或 Anaconda 后再运行本脚本。' -ForegroundColor Red
    exit 1
}
$ver = python --version 2>&1
Write-Host ("已检测到：" + $ver)

# 2. 安装依赖
Write-Host ''
Write-Host '[1/2] 尝试通过默认源安装（requirements.txt）...'
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '默认源安装失败（常见于国内网络 HTTPS 被阻断），改用阿里云 HTTP 镜像重试...' -ForegroundColor Yellow
    python -m pip install -r requirements.txt --index-url http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host '[错误] 安装失败。请手动执行并检查网络：' -ForegroundColor Red
        Write-Host '  python -m pip install pynacl'
        exit 1
    }
}

# 3. 验证 PyNaCl
Write-Host ''
Write-Host '[2/2] 验证 PyNaCl 是否可用...'
python -c "import nacl; print('PyNaCl', nacl.__version__)"
if ($LASTEXITCODE -ne 0) {
    Write-Host '注意：未检测到 PyNaCl，weather.py 将回退使用系统 openssl 签名，' -ForegroundColor Yellow
    Write-Host '      要求 openssl 1.1.1+（Anaconda 自带 1.0.2k 不支持 Ed25519）。'
} else {
    Write-Host 'PyNaCl 可用。'
}

Write-Host ''
Write-Host '安装完成！'
