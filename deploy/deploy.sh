#!/usr/bin/env bash
#
# P1 知识库平台 · 一键推送部署脚本 v2
#
# 本机要求：
#   - Windows 用 Git Bash 运行（自带 tar/scp/ssh）
#   - 目标服务器：Ubuntu 22.04 / Debian 12 / CentOS Stream 9 / Rocky 9（自动识别 apt/yum）
#   - 已买好云服务器，能 SSH 登录（公网 IP + 用户名）
#
# 使用前先填下面 4 个变量（★ 必填）：
#   SERVER_IP    服务器公网 IP（★）
#   SSH_USER     SSH 登录用户名，默认 root（★ 非 root 请改）
#   DOMAIN       你的域名（有则自动配 Caddy + 免费 HTTPS；留空则 IP 裸跑，仅临时演示）
#   SSH_PASSWORD SSH 密码（可留空；留空则每步 ssh/scp 会交互提示输密码。
#                 【推荐】先执行： ssh-copy-id 用户名@IP 换密钥，之后无需密码）
#
# 用法示例：
#   SERVER_IP=1.2.3.4 SSH_USER=root DOMAIN=kb.example.com bash deploy.sh
#   SERVER_IP=1.2.3.4 SSH_USER=root bash deploy.sh          # 无域名：IP:8000 裸跑
#
# 执行流程：本地打包(排除 venv/数据/.env) → scp 上传 → 服务器装 Docker →
#           配 .env.prod → compose 构建启动 → seed 演示数据 → (有域名) Caddy+HTTPS → 防火墙

set -euo pipefail

# ====================== ★★★ 必填变量（改这里） ★★★ ======================
SERVER_IP="${SERVER_IP:?请先设置 SERVER_IP（如 SERVER_IP=1.2.3.4）}"
SSH_USER="${SSH_USER:-root}"
DOMAIN="${DOMAIN:-}"            # 留空则不启用 Caddy/HTTPS
SSH_PASSWORD="${SSH_PASSWORD:-}" # 留空则交互输密码；建议用 ssh-copy-id 换密钥
# ======================================================================

ARCHIVE="p1_knowledge_platform.tar.gz"
REMOTE_DIR="/opt/p1_knowledge_platform"
# 脚本所在 deploy/ 的上一级 = 项目根
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> 项目根: $PROJECT_DIR"
echo "==> 目标: $SSH_USER@$SERVER_IP:$REMOTE_DIR"

# ---- SSH 前缀：有密码用 sshpass（需已安装），否则原样（交互输密码）----
SSH_BASE="ssh -o StrictHostKeyChecking=no"
SCP_BASE="scp -o StrictHostKeyChecking=no"
if [ -n "$SSH_PASSWORD" ]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "[警告] 设置了 SSH_PASSWORD 但本机没有 sshpass（Windows Git Bash 需自行安装）。"
    echo "       将改为交互输密码方式，或建议用 ssh-copy-id 换密钥。"
  else
    SSH_BASE="sshpass -p '$SSH_PASSWORD' ssh -o StrictHostKeyChecking=no"
    SCP_BASE="sshpass -p '$SSH_PASSWORD' scp -o StrictHostKeyChecking=no"
  fi
fi

# ====================== ① 本机打包 + 上传 ======================
echo "==> [本机] 打包（排除 .venv / 数据 / 本地 .env）..."
cd "$(dirname "$PROJECT_DIR")"     # 到父目录打包，归档带 p1_knowledge_platform/ 前缀
tar --exclude='.venv' --exclude='.pytest_cache' --exclude='.idea' \
    --exclude='data/db.sqlite3' --exclude='data/vectors' --exclude='data/uploads' \
    --exclude='data/logs' --exclude='.env' \
    -czf "$ARCHIVE" "$(basename "$PROJECT_DIR")"

echo "==> [本机] 上传到服务器 $REMOTE_DIR ..."
eval "$SSH_BASE $SSH_USER@$SERVER_IP \"mkdir -p $REMOTE_DIR\""
eval "$SCP_BASE $ARCHIVE $SSH_USER@$SERVER_IP:$REMOTE_DIR/"

# ====================== ② 服务器侧初始化 ======================
echo "==> [服务器] 解压 + 安装 Docker + 启动服务..."
eval "$SSH_BASE $SSH_USER@$SERVER_IP \"REMOTE_DIR='$REMOTE_DIR' DOMAIN='$DOMAIN' bash -s\"" <<'REMOTE_EOF'
set -euo pipefail
cd "$REMOTE_DIR"
tar -xzf p1_knowledge_platform.tar.gz
cd p1_knowledge_platform/deploy

# --- 系统自检：apt(Ubuntu/Debian) 或 yum/dnf(CentOS/Rocky) ---
if command -v apt-get >/dev/null 2>&1; then
  PKG="apt-get"; FW="ufw"
elif command -v dnf >/dev/null 2>&1; then
  PKG="dnf"; FW="firewalld"
elif command -v yum >/dev/null 2>&1; then
  PKG="yum"; FW="firewalld"
else
  echo "[错误] 无法识别系统包管理器（仅支持 apt/dnf/yum）"; exit 1
fi
echo "==> 检测到包管理器: $PKG, 防火墙: $FW"

# --- 安装 Docker（已装则跳过）---
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi
if ! docker compose version >/dev/null 2>&1; then
  $PKG update -y 2>/dev/null || true
  $PKG install -y docker-compose-plugin
fi

# --- 生产环境变量（复用项目自带的 .env.prod，含真实 DeepSeek key）---
if [ ! -f .env.prod ]; then cp .env.prod.example .env.prod; fi
chmod 600 .env.prod

# --- 端口与安全项：有域名才收紧端口并启用 HTTPS 相关项 ---
if [ -n "$DOMAIN" ]; then
  sed -i 's#"8000:8000"#"127.0.0.1:8000:8000"#' docker-compose.yml   # 仅本机，Caddy 反代
  sed -i 's#^ENABLE_DOCS=.*#ENABLE_DOCS=false#' .env.prod
  sed -i 's#^FORCE_HTTPS_HEADERS=.*#FORCE_HTTPS_HEADERS=true#' .env.prod
  sed -i "s#^CORS_ORIGINS=.*#CORS_ORIGINS=[\"https://$DOMAIN\"]#" .env.prod
else
  # 无域名：保持 8000 直暴露公网（临时演示用），不启用 HSTS
  sed -i 's#^ENABLE_DOCS=.*#ENABLE_DOCS=false#' .env.prod
  sed -i 's#^FORCE_HTTPS_HEADERS=.*#FORCE_HTTPS_HEADERS=false#' .env.prod
fi

# --- 构建并启动 ---
docker compose up -d --build
echo "==> 等待健康检查..."
ok=""
for i in $(seq 1 30); do
  if curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1; then ok=1; break; fi
  sleep 3
done
if [ -n "$ok" ]; then echo "  [健康检查通过]"; else echo "  [健康检查未通过，请 docker compose logs -f kb-app 排查]"; fi

# --- 初始化演示数据（幂等，首次必做）---
docker compose run --rm kb-app python scripts/seed_data.py

# --- 有域名：Caddy 反代 + 免费 HTTPS ---
if [ -n "$DOMAIN" ]; then
  echo "==> 安装 Caddy 并配置 HTTPS..."
  $PKG install -y debian-keyring debian-archive-keyring apt-transport-https curl 2>/dev/null || true
  curl -1sLf 'https://dl.cloudflare-cdn.com/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable.gpg \
    || curl -fsSL 'https://caddy-io.b-cdn.net/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable.gpg
  echo "deb [signed-by=/usr/share/keyrings/caddy-stable.gpg] https://dl.cloudflare-cdn.com/caddy/deb/stable/debian all main" > /etc/apt/sources.list.d/caddy.list \
    || true
  $PKG update -y 2>/dev/null || true
  $PKG install -y caddy || echo "[警告] Caddy 安装失败，可稍后手动安装（见 deploy/Caddyfile）"
  cat > /etc/caddy/Caddyfile <<CADDY_EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:8000
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
}
CADDY_EOF
  systemctl enable --now caddy
  echo "==> 访问 https://$DOMAIN （演示账号 admin/admin123，首次登录强制改密）"
else
  echo "==> 未配置域名，临时访问 http://$SERVER_IP:8000"
  echo "    生产环境请配置域名 + Caddy（见 deploy/Caddyfile）以启用 HTTPS"
fi

# --- 防火墙放行 ---
if [ "$FW" = "ufw" ]; then
  ufw allow 22/tcp 2>/dev/null || true
  ufw allow 80/tcp 2>/dev/null || true
  ufw allow 443/tcp 2>/dev/null || true
  ufw --force enable 2>/dev/null || true
elif [ "$FW" = "firewalld" ]; then
  firewall-cmd --permanent --add-service=ssh 2>/dev/null || true
  firewall-cmd --permanent --add-service=http 2>/dev/null || true
  firewall-cmd --permanent --add-service=https 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
fi
REMOTE_EOF

echo ""
echo "==> 部署流程执行完毕。"
echo "    ★ 最后一步（云控制台操作）：安全组入站放行 22/80/443（8000 仅在服务器本机监听，不对外）。"
echo "    ★ 首次登录 admin/admin123 会强制改密，上线后请停用 editor/viewer 演示账号。"
