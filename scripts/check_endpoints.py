"""逐条体检本项目依赖的公共接口，输出一张 Markdown 表。

用法（Windows）：
    .venv\\Scripts\\python.exe scripts\\check_endpoints.py

只用标准库，不依赖项目环境之外的包，方便在任何机器上先跑这一条。
结果同时打印到终端并写入 reports/endpoint_check_<日期>.md。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import time
import urllib.error
import urllib.request

UA = "glyco-analysis-endpoint-check/0.1 (student research)"
TIMEOUT = 45
MAX_BYTES = 3 * 1024 * 1024

# (名称, 用途, URL, 判定说明)
PROBES = [
    (
        "UniProt REST",
        "人类糖蛋白实验证据检索（F1 数据源）",
        "https://rest.uniprot.org/uniprotkb/search"
        "?query=ft_carbohyd_exp:%2A+AND+reviewed:true+AND+organism_id:9606"
        "&size=1&fields=accession",
        "期望 200，且 X-Total-Results = 1381",
    ),
    (
        "GlyGen",
        "单蛋白糖基化详情（F1 位点证据）",
        "https://api.glygen.org/protein/detail/P01857/",
        "必须 GET；POST 会 500；响应约 600 KB",
    ),
    (
        "GlyConnect",
        "糖蛋白/糖链关联（F2 备选数据源）",
        "https://glyconnect.expasy.org/api/proteins?format=json&limit=1",
        "文档给的路径 2026-10-18 不通，这里探活",
    ),
    (
        "GlyTouCan",
        "糖链结构标识（F2/F3 结构查询）",
        "https://api.glytoucan.org/glycan/list",
        "文档给的路径 2026-10-18 返回 404，这里探活",
    ),
    (
        "KEGG REST",
        "通路信息（F3 工具之一）",
        "https://rest.kegg.jp/info/pathway",
        "期望 200 且返回纯文本",
    ),
    (
        "PubChem PUG REST",
        "化合物属性查询（F3 工具之一）",
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/glucose"
        "/property/MolecularFormula/JSON",
        "期望 200 且 JSON 内含 MolecularFormula",
    ),
]


def _fetch(url: str) -> tuple[int, dict[str, str], bytes, float]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(MAX_BYTES)
            elapsed = time.perf_counter() - started
            return resp.status, dict(resp.headers), body, elapsed
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BYTES) if exc.fp else b""
        elapsed = time.perf_counter() - started
        return exc.code, dict(exc.headers or {}), body, elapsed


def _evidence(name: str, headers: dict[str, str], body: bytes) -> str:
    if name == "UniProt REST":
        total = headers.get("X-Total-Results") or headers.get("x-total-results")
        return f"X-Total-Results={total}" if total else "缺少 X-Total-Results"
    if name == "PubChem PUG REST":
        try:
            data = json.loads(body.decode("utf-8", "replace"))
            formula = data["PropertyTable"]["Properties"][0]["MolecularFormula"]
            return f"MolecularFormula={formula}"
        except Exception:
            return "JSON 解析失败"
    text = body.decode("utf-8", "replace").strip().replace("\n", " ")
    return (text[:90] + "…") if len(text) > 90 else (text or "（空响应）")


def run() -> list[dict]:
    rows = []
    for name, purpose, url, note in PROBES:
        row = {"name": name, "purpose": purpose, "url": url, "note": note}
        try:
            status, headers, body, elapsed = _fetch(url)
            row.update(
                status=status,
                ms=round(elapsed * 1000),
                size=len(body),
                evidence=_evidence(name, headers, body),
            )
        except Exception as exc:  # 网络层失败（超时 / DNS / TLS）
            row.update(status=None, ms=None, size=0, evidence=f"{type(exc).__name__}: {exc}")
        rows.append(row)
    return rows


def render(rows: list[dict]) -> str:
    today = dt.date.today().isoformat()
    ok = sum(1 for r in rows if r["status"] == 200)
    lines = [
        f"# 接口体检 {today}",
        "",
        f"- 主机：{platform.node()} · {platform.system()} {platform.release()}",
        f"- Python：{platform.python_version()}",
        f"- 结果：**{ok}/{len(rows)} 个接口返回 200**",
        "",
        "| 接口 | 用途 | 状态 | 延迟 | 大小 | 证据 | 备注 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        status = r["status"] if r["status"] is not None else "ERR"
        ms = f"{r['ms']} ms" if r["ms"] is not None else "-"
        size = f"{r['size'] / 1024:.0f} KB" if r["size"] else "-"
        evidence = str(r["evidence"]).replace("|", "\\|")
        lines.append(
            f"| {r['name']} | {r['purpose']} | `{status}` | {ms} | {size} | {evidence} | {r['note']} |"
        )
    lines += [
        "",
        "> 判定口径：`200` 可用；`4xx/5xx` 记为不可用，需换路径或换数据源；`ERR` 是网络层失败。",
        "> 同一接口连续两次失败再下结论，单次超时可能只是网络抖动。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    rows = run()
    report = render(rows)
    print(report)
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"endpoint_check_{dt.date.today().isoformat()}.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"已写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
