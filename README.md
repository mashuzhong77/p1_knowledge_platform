# P1 知识库管理平台

面向建筑规范 / 绿建 / 双碳领域的知识库管理平台：文档导入、知识单元管理、四类数据权限、RAG 问答（SSE 流式）、数据看板、FAQ 沉淀、知识缺口、审计日志与版本管理。

## 快速开始

```bash
# 1. 安装依赖（本机 Anaconda 已具备大部分）
pip install -r requirements.txt

# 2. 配置环境（可选）
copy .env.example .env
# 填写 LLM_API_KEY（或遗留别名 DEEPSEEK_API_KEY）；无 key 时问答走离线降级
# EMBEDDING_MODEL 默认 hash（免下载模型）；远程 BGE-M3 / reranker 配置见 .env.example 注释

# 3. 初始化演示数据（账号 admin/admin123、editor/123456、viewer/123456）
python scripts/seed_data.py

# 4. 启动
python run.py
# 浏览器打开 http://127.0.0.1:8000

# 5. 运行测试
python -m pytest tests -v
```

## 主要接口

- `POST /api/auth/login`：登录
- `POST /api/knowledge/import-text`、`POST /api/knowledge/import`：导入
- `GET /api/knowledge/import/status/{task_id}`：导入任务进度（异步导入轮询）
- `GET /api/knowledge/units`：知识单元列表（按数据权限过滤）
- `POST /api/ai/chat/stream`：SSE 流式问答（鉴权过滤 + 引用 + 权限提示）
- `GET /api/dashboard/metrics`：看板统计
- `GET /api/settlement/faqs/recommendations`：FAQ 推荐
- `GET /api/settlement/knowledge-gaps`：知识缺口
- `GET /api/audit/logs`：审计日志

## 说明

- 演示账号密码为明文示例，正式环境必须接入真实认证体系。
- 示例语料标注为教学资料，正式使用请替换为官方标准原文。
- 问答链路（2026-08-18 增强）：FAQ 缓存命中直返 → 问句改写（历史消解 + 知识域识别）→ 混合检索 + HyDE + RRF 融合 →（可选远程 rerank 重排）→（可选 MMR 去冗余）→ 动态截断 → 证据链校验；无 API key 时改写/HyDE 自动降级，链路不变。SSE 真 token 流式（逐 token 推送），流末尾含 `model` 事件展示当前模型。
- P3 微调模型接入：`LLM_API_KEY/BASE_URL/MODEL` 三个全填（BASE_URL 填 vLLM 地址、MODEL 填 vLLM 模型名）；远程 BGE-M3 配 `EMBEDDING_API_URL`，远程 reranker 配 `RERANK_API_URL`（均默认关闭）；切换向量实现（hash 256 维 ↔ BGE-M3 1024 维）需删 `data/vectors` 后重新导入。检索参数（`.env` 可配，见 `.env.example`）：`TOP_K/RRF_K/W_BM25/W_VEC/RECALL_MULTIPLIER/MMR_ENABLED/MMR_LAMBDA/MMR_TOP`；本地小库默认 `TOP_K=5`，生产建议调 8-10 并开 `MMR_ENABLED=true`。
- 密级权限：知识单元 `security_level`（open/internal/confidential）参与访问判定，confidential 需 `knowledge:confidential` 权限码（admin 默认拥有）。
