# 部署说明（P1 知识库管理平台）

参考课程文档：《应用服务部署.md》《GPU模型部署.md》

## 文件结构

```text
deploy/
├── Dockerfile               # 业务服务镜像（python:3.11-slim + uvicorn，已启用 --proxy-headers）
├── docker-compose.yml       # 单服务版：仅 kb-app（SQLite + ChromaDB 数据卷持久化）
├── .env.prod.example        # 生产环境变量模板
├── Caddyfile                # 反向代理 + TLS 参考配置（上线必做）
├── DEPLOY_CHECKLIST.md      # 部署 checklist
└── README.md
```

## 快速启动

```bash
cd deploy
cp .env.prod.example .env.prod
# 编辑 .env.prod，填写 DEEPSEEK_API_KEY（无 key 走离线降级）

docker compose up -d --build

# 初始化演示数据（账号 admin/admin123、editor/123456、viewer/123456，首次登录会强制修改初始密码）
docker compose run --rm kb-app python scripts/seed_data.py

# 健康检查
curl http://127.0.0.1:8000/health

# 查看日志 / 停止
docker compose logs -f kb-app
docker compose down
```

## 端口规划

- 公网只开放：`443`（HTTPS）、`22`（SSH）；`8000` 由 Caddy/nginx 反代转发，不暴露公网

## 反向代理与 HTTPS（上线必做）

- 参考 `deploy/Caddyfile`（或 nginx），TLS 终结在 uvicorn 前；uvicorn 已启用 `--proxy-headers`
- `.env.prod` 置 `FORCE_HTTPS_HEADERS=true`（HSTS）、`ENABLE_DOCS=false`、`CORS_ORIGINS=["https://你的域名"]`
- 本地明文 HTTP 开发必须保持 `FORCE_HTTPS_HEADERS=false`（HSTS over HTTP 会坏浏览器）

## 注意事项

- 首次启动必须先执行 seed 脚本，否则知识库为空
- 容器内默认 `EMBEDDING_MODEL=hash`（免下载模型）；如需 BGE-M3 需保证容器可访问模型下载源
- 镜像包含 sentence-transformers/chromadb/pdfplumber，体积较大，首次构建较慢
- 数据持久化在 `deploy/volumes/`，删除前请备份
