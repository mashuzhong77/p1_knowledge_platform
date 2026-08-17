"""内存态任务进度注册表（框架 R7，蒸馏自 ai_0302 task_utils）。"""

import threading

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

NODE_CN = {
    "upload_file": "上传文件",
    "import": "导入入库",
    "qa": "问答分析",
}

_TASKS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _cn(node: str) -> str:
    return NODE_CN.get(node, node)


def create_task(task_id: str) -> None:
    with _LOCK:
        _TASKS[task_id] = {
            "status": STATUS_PENDING,
            "done_list": [],
            "running_list": [],
            "result": None,
            "error": "",
        }


def update_task_status(task_id: str, status: str) -> None:
    with _LOCK:
        if task_id in _TASKS:
            _TASKS[task_id]["status"] = status


def add_done_task(task_id: str, node: str) -> None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return
        running = task["running_list"]
        task["running_list"] = [n for n in running if n != node]
        if _cn(node) not in task["done_list"]:
            task["done_list"].append(_cn(node))


def set_task_result(task_id: str, result) -> None:
    with _LOCK:
        if task_id in _TASKS:
            _TASKS[task_id]["result"] = result


def set_task_error(task_id: str, error: str) -> None:
    with _LOCK:
        if task_id in _TASKS:
            _TASKS[task_id]["error"] = error


def get_task(task_id: str) -> dict | None:
    with _LOCK:
        task = _TASKS.get(task_id)
        return dict(task) if task else None


def clear_task(task_id: str) -> None:
    with _LOCK:
        _TASKS.pop(task_id, None)
