"""启动入口：python run.py

端口绑定说明：
- 默认使用 settings.host / settings.port（127.0.0.1:8000）。
- 若该端口已被占用（典型报错 [Errno 10048] / winerror 10048），会自动顺延到下一个
  空闲端口（8001, 8002 ...），并在启动日志中打印实际访问地址，避免「启动即失败」。
- 如果想固定使用 8000，请先释放占用 8000 的进程（见下方提示），或显式改端口。
"""

import socket

import uvicorn

from app.config import settings


def resolve_port(host: str, preferred: int, max_tries: int = 20) -> int:
    """从 preferred 起，找第一个可绑定的端口（含 preferred 本身）。"""
    for port in range(preferred, preferred + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return preferred  # 兜底：都失败就让 uvicorn 抛出原始错误


if __name__ == "__main__":
    port = resolve_port(settings.host, settings.port)
    if port != settings.port:
        print(
            f"[端口避让] {settings.host}:{settings.port} 已被占用，"
            f"自动改用 {settings.host}:{port}"
        )
    print(f"知识库平台已启动: http://{settings.host}:{port}")
    uvicorn.run("app.main:app", host=settings.host, port=port, reload=False)
