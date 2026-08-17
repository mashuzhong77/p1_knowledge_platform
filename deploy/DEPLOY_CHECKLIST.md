# P1 知识库管理平台 · 服务器部署 Checklist

> 目标：把项目部署到服务器（Docker + Compose，最小版），跑通健康检查、初始化数据、验证问答。
> 配套文件：`deploy/README.md`（启动/停服/日志命令）、`deploy/docker-compose.yml`、`deploy/Dockerfile`、`deploy/.env.prod.example`。

---

## 阶段 0：部署前准备（本地完成）

- [ ] 确认服务器信息：IP / 域名、SSH 账号、登录方式（密钥或密码）
- [ ] 确认服务器系统（Ubuntu/CentOS/Debian）与 Docker 安装方式
- [ ] 在服务器开放端口规划（按 `deploy/README.md`）：
  - 公网开放：`443`（HTTPS）、`22`（SSH）；`8000` 仅对内/本机（由 Caddy/nginx 反代转发）
  - 其余端口一律不暴露公网
- [ ] 准备 `.env.prod` 需要的环境变量：
  - `DEEPSEEK_API_KEY`（本机 `.env` 里已有，填服务器用同一把 key 或服务端独立 key）
  - `EMBEDDING_MODEL`：默认 `hash`（免下载模型，离线可用）；有 GPU/网络可改 `BAAI/bge-m3`
- [ ] 确认本机已装 Docker（用于本地先构建镜像自检）——本机 Docker 当前不可用，若先本地自检需先启动 Docker Desktop

---

## 阶段 1：项目上传到服务器

- [ ] 压缩项目（排除无关文件）：
  ```bash
  cd d:\mashu77\workspace\project1
  tar --exclude='.venv' --exclude='.pytest_cache' --exclude='.idea' \
      --exclude='data/db.sqlite3' --exclude='data/vectors' --exclude='data/uploads' \
      --exclude='data/logs' --exclude='.env' \
      -czf p1_knowledge_platform.tar.gz p1_knowledge_platform
  ```
  > 数据目录（db.sqlite3 / vectors / uploads）是本地运行产物，**不要带上服务器**，用 seed 脚本重建；`.env` 是本地 LLM 配置，服务器用 `.env.prod`。
- [ ] 上传到服务器，例如：
  ```bash
  scp p1_knowledge_platform.tar.gz root@<服务器IP>:/opt/
  ```
- [ ] 服务器解压：
  ```bash
  ssh root@<服务器IP>
  cd /opt && tar -xzf p1_knowledge_platform.tar.gz && cd p1_knowledge_platform
  ```

---

## 阶段 2：服务器环境准备

- [ ] 安装 Docker + Compose 插件（如未安装）：
  ```bash
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
  docker compose version   # 确认 compose 可用
  ```
- [ ] 创建生产环境变量文件：
  ```bash
  cd /opt/p1_knowledge_platform/deploy
  cp .env.prod.example .env.prod
  vim .env.prod   # 填入 DEEPSEEK_API_KEY；EMBEDDING_MODEL 按需保持 hash
  ```
- [ ] 确认磁盘/内存满足：
  - 镜像含 sentence-transformers / chromadb / pdfplumber，构建体积较大（数 GB 级）
  - 建议 ≥ 4GB 内存、≥ 10GB 空闲磁盘（含镜像与数据卷）

---

## 阶段 3：构建并启动

- [ ] 构建镜像并启动：
  ```bash
  cd /opt/p1_knowledge_platform/deploy
  docker compose up -d --build
  ```
  > 首次构建较慢（腾讯云镜像源已配好，失败自动回退官方源）。
- [ ] 确认容器运行：
  ```bash
  docker compose ps        # kb-app 状态应为 running (healthy)
  docker compose logs -f kb-app
  ```
- [ ] 初始化演示数据（**首次必做，否则知识库为空**）：
  ```bash
  docker compose run --rm kb-app python scripts/seed_data.py
  ```
  - 演示账号：`admin/admin123`、`editor/123456`、`viewer/123456`

---

## 阶段 3.5：反向代理与 HTTPS（上线必做）

- [ ] 在服务器装 Caddy（或 nginx），参考 `deploy/Caddyfile`：TLS 终结 + 反代到 `127.0.0.1:8000`
- [ ] `.env.prod` 置 `FORCE_HTTPS_HEADERS=true`（启用 HSTS）、`ENABLE_DOCS=false`、`CORS_ORIGINS=["https://你的域名"]`
- [ ] 确认 uvicorn 已启用 `--proxy-headers`（Dockerfile 已配置），否则取不到真实客户端地址
- [ ] 公网只开放 `443`（HTTPS）、`22`（SSH）；`8000` 不暴露公网

---

## 阶段 4：验证

- [ ] 健康检查：
  ```bash
  curl http://127.0.0.1:8000/health      # 期望 {"status":"ok"}
  ```
- [ ] 从本机/公网访问 `http://<服务器IP>:8000` 打开前端页面
- [ ] 登录任一演示账号
- [ ] 导入一条文档（文本或文件），确认入库
- [ ] 发一条问答，确认 SSE 流式回答（有 key 走 DeepSeek，无 key 会返回"离线演示模式"）
- [ ] 查看 `GET /api/dashboard/metrics` 有统计
- [ ] 检查 `data/uploads/`、`data/db.sqlite3`、`data/vectors/` 已生成数据

---

## 阶段 5：收尾与安全

- [ ] 确认 `deploy/.env.prod` 权限收紧：`chmod 600 deploy/.env.prod`
- [ ] 确认公网只暴露 `443`（HTTPS），SSH 建议禁用密码登录（改用密钥）
- [ ] 演示账号已设 `must_change_password`（seed 后首次登录强制改密）；上线后务必为正式账号改密并停用演示账号
- [ ] 数据持久化确认：数据在 `deploy/volumes/data`（宿主机），删除容器不丢数据；**删除前备份**
- [ ] 备份策略：`deploy/volumes/` 定期备份（含 sqlite + 上传文件 + 向量库）
- [ ] 重启策略：compose 已配 `restart: unless-stopped`，服务器重启后自动拉起

---

## 常用运维命令

| 操作 | 命令 |
|---|---|
| 查看状态 | `docker compose ps` |
| 查看日志 | `docker compose logs -f kb-app` |
| 重启 | `docker compose restart kb-app` |
| 停止 | `docker compose down` |
| 重新构建 | `docker compose up -d --build` |
| 备份数据 | `tar -czf volumes_backup.tar.gz volumes/` |

---

## 回滚预案

- [ ] 保留上一个可用的镜像 tag 或备份 `volumes/`，出问题可回退
- [ ] 升级流程：备份 volumes → 重新 build → seed（幂等，重复导入会提示）→ 验证

## 遗留事项（生产演进，非本次部署阻塞项）

- [ ] 中间件（Milvus/MinIO/MongoDB）已移除——代码未接入、纯预留无用；如需未来引入需新增向量库/对象存储/文档库适配器后再启用
- [ ] 演示账号明文密码仅为示例，正式使用必须接入真实认证体系
- [ ] 示例语料为教学资料，正式使用请替换为官方标准原文
