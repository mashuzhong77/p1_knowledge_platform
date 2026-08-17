"""文档切片：标题分节 + 最大长度切分。"""


def chunk_text(text: str, max_chars: int = 800, overlap: int = 80) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = max(
                text.rfind("\n", start + 1, end),
                text.rfind("。", start + 1, end),
                text.rfind(". ", start + 1, end),
            )
            if cut > start:
                end = cut + 1
        chunks.append(text[start:end])
        nxt = end - overlap
        start = nxt if nxt > start else start + 1
    return chunks


def parse_markdown_units(text: str) -> list[dict]:
    """按一级标题（# ）分节，返回 [{title, content}]。"""
    units: list[dict] = []
    title = "未命名"
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        content = "\n".join(buf).strip()
        if content:
            units.append({"title": title, "content": content})
        buf = []

    for line in (text or "").splitlines():
        if line.startswith("# "):
            flush()
            title = line[2:].strip() or "未命名"
        else:
            buf.append(line)
    flush()
    return units


def refine_units(
    units: list[dict],
    *,
    max_chars: int = 800,
    min_chars: int = 200,
    overlap: int = 80,
) -> list[dict]:
    """长切短合（框架 R5）：超长单元按语义断点拆分并编号；过短同标题单元合并且不超上限。"""
    out: list[dict] = []
    for u in units:
        title = (u.get("title") or "未命名").strip()
        content = (u.get("content") or "").strip()
        if not content:
            continue
        if len(content) > max_chars:
            for i, piece in enumerate(chunk_text(content, max_chars=max_chars, overlap=overlap), start=1):
                out.append({"title": f"{title}-{i}", "content": piece.strip()})
        else:
            out.append({"title": title, "content": content})

    merged: list[dict] = []
    for u in out:
        if (
            merged
            and len(merged[-1]["content"]) < min_chars
            and merged[-1]["title"] == u["title"]
            and len(merged[-1]["content"]) + len(u["content"]) <= max_chars
        ):
            merged[-1]["content"] += "\n\n" + u["content"]
        else:
            merged.append(dict(u))
    return merged
