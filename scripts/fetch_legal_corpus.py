"""法规数据抓取脚本（二期 Task 26）：批量抓取 12 部「网络安全与数据合规」法规原文 → Markdown。

手动执行（真实网络，不在 pytest 内）：`python scripts/fetch_legal_corpus.py`

数据源红线（决策文档 §6.2）：只用一手官方文本——
npc.gov.cn（人大网）/ gov.cn（中国政府网）/ cac.gov.cn（网信办）/
gjbmj.gov.cn（国家保密局）/ court.gov.cn（最高人民法院）。

产出：
- data/legal/{法规名}.md —— 抽取后的 Markdown 正文；
- data/legal/manifest.json —— 名称、位阶、来源 URL、抓取时间、正文长度。

抓取遵守 robots + 仅抓官方公开法条页，量小（12 篇），复用 webpage.fetch_and_extract。
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# 脚本位于仓库根 scripts/，app 包在 backend/ 下：锚定后任意工作目录可执行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.parsers.webpage import fetch_and_extract  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "legal"

# 12 部法规清单（决策文档 §6.5，按法律位阶分四层）
# 每项：(文件名 stem, 显示名, 位阶, 来源 URL)
CORPUS = [
    # 第一层 · 法律（4 部）
    ("网络安全法", "中华人民共和国网络安全法", "法律",
     "https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm"),
    ("数据安全法", "中华人民共和国数据安全法", "法律",
     "https://www.gjbmj.gov.cn/n1/2026/0911/c462638-40797231.html"),
    ("个人信息保护法", "中华人民共和国个人信息保护法", "法律",
     "http://www.npc.gov.cn/npc/c2/c30834/202108/t20210820_313088.html"),
    ("密码法", "中华人民共和国密码法", "法律",
     "http://www.npc.gov.cn/npc/c1773/c1848/c21114/c36794/c36798/201910/t20191028_301735.html"),
    # 第二层 · 行政法规（3 部）
    ("网络数据安全管理条例", "网络数据安全管理条例", "行政法规",
     "https://www.cac.gov.cn/2024-09/30/c_1729384452307680.htm"),
    ("关键信息基础设施安全保护条例", "关键信息基础设施安全保护条例", "行政法规",
     "https://www.cac.gov.cn/2021-08/17/c_1630785976988160.htm"),
    ("未成年人网络保护条例", "未成年人网络保护条例", "行政法规",
     "https://www.12377.cn/xzfg/2023/3cdab3f2_web.html"),
    # 第三层 · 部门规章（3 部）
    ("数据出境安全评估办法", "数据出境安全评估办法", "部门规章",
     "https://www.cac.gov.cn/2022-07/07/c_1658811536396503.htm"),
    ("个人信息出境标准合同办法", "个人信息出境标准合同办法", "部门规章",
     "https://www.cac.gov.cn/2023-02/24/c_1678884830036813.htm"),
    ("网络安全审查办法", "网络安全审查办法", "部门规章",
     "https://www.cac.gov.cn/2022-01/04/c_1642894602182845.htm"),
    # 第四层 · 司法解释（2 部）
    ("侵犯公民个人信息刑事案件司法解释",
     "最高人民法院、最高人民检察院关于办理侵犯公民个人信息刑事案件适用法律若干问题的解释",
     "司法解释",
     "https://www.court.gov.cn/fabu/xiangqing/43942.html"),
    ("人脸识别民事案件司法解释",
     "最高人民法院关于审理使用人脸识别技术处理个人信息相关民事案件适用法律若干问题的规定",
     "司法解释",
     "https://www.court.gov.cn/zixun/xiangqing/315851.html"),
]


def _sanitize_md(md: str, name: str) -> str:
    """正文头部补一级标题，保证切块器能识别文档标题边界。"""
    lines = md.splitlines()
    # 若首行已是标题（# 开头），保留；否则补一级标题
    if lines and lines[0].lstrip().startswith("#"):
        return md
    return f"# {name}\n\n{md}"


def _main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "items": []}
    ok, fail = 0, 0

    for stem, name, rank, url in CORPUS:
        try:
            print(f"[抓取] {name} …", flush=True)
            html, md = fetch_and_extract(url)
            md = _sanitize_md(md, name)
            out_path = OUT_DIR / f"{stem}.md"
            out_path.write_text(md, encoding="utf-8")
            manifest["items"].append({
                "name": name,
                "rank": rank,
                "source_url": url,
                "file": f"{stem}.md",
                "chars": len(md),
            })
            print(f"       → {out_path.name} ({len(md)} 字)", flush=True)
            ok += 1
        except Exception as e:  # noqa: BLE001 —— 单篇失败不影响其余
            print(f"       ✗ 失败：{e}", flush=True)
            manifest["items"].append({
                "name": name, "rank": rank, "source_url": url, "error": str(e),
            })
            fail += 1

    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n完成：成功 {ok} / 失败 {fail}，产物在 {OUT_DIR}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(_main())
