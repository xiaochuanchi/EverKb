"""版本号同步：以仓库根 VERSION 文件为唯一源，同步到三处落点。

三个应用（backend / admin / web）共用同一个产品版本号（lockstep），
tag 打 vX.Y.Z，变更记录见 CHANGELOG.md。

落点：
- admin/package.json                          顶层 "version" 字段
- admin/.env.development|production|example   VITE_VERSION（vite define 注入 __APP_VERSION__）
- web/package.json                            顶层 "version" 字段
- backend/app/main.py                         APP_VERSION 常量（/health 与 FastAPI(version=) 共用）

用法（仓库根执行）：
- python3 scripts/sync_version.py          # 把 VERSION 写入三处（发版时跑）
- python3 scripts/sync_version.py --check  # 只校验一致性，漂移时退出码 1（CI 用）

发版流程：改 VERSION → 跑同步 → 提交 → 打 vX.Y.Z tag。
"""
import argparse
import re
import sys
from pathlib import Path

# 脚本位于仓库根 scripts/：锚定仓库根，任意工作目录可执行
ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"

# semver（允许预发布后缀，如 1.2.0-rc.1）
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")

# package.json 顶层 "version"：2 空格缩进锚定，不会误伤依赖里的版本串
PKG_VERSION_RE = re.compile(r'^(  "version": ")[^"]*(",)$', re.MULTILINE)

# admin .env 的 VITE_VERSION（前端构建注入 __APP_VERSION__，用户中心展示）；
# 组 2 是版本号后的尾部（行尾空白/CR），保持 _replace 统一的「前缀+版本+后缀」结构
ENV_VERSION_RE = re.compile(r"^(VITE_VERSION\s*=\s*)\S+(\s*)$", re.MULTILINE)

# main.py 的 APP_VERSION 常量行（/health 与 FastAPI(version=) 共用；失配会显式报错而非静默跳过）
MAIN_VERSION_RE = re.compile(r'^(\s*APP_VERSION = ")[^"]*(")$', re.MULTILINE)

# (仓库根相对路径, 落点正则)
TARGETS: list[tuple[str, re.Pattern[str]]] = [
    ("admin/package.json", PKG_VERSION_RE),
    ("admin/.env.development", ENV_VERSION_RE),
    ("admin/.env.production", ENV_VERSION_RE),
    ("admin/.env.example", ENV_VERSION_RE),
    ("web/package.json", PKG_VERSION_RE),
    ("backend/app/main.py", MAIN_VERSION_RE),
]


def read_version() -> str:
    """读 VERSION 文件并校验格式，非法直接退出非 0。"""
    text = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not SEMVER_RE.match(text):
        print(f"错误：VERSION 内容非法：{text!r}（需要 semver，如 0.1.0 或 1.0.0-rc.1）")
        sys.exit(1)
    return text


def _replace(text: str, pattern: re.Pattern[str], version: str, rel: str) -> str:
    """把落点行的版本号替换为 version；命中数不是 1 视为文件结构变化，显式报错。"""
    new, n = pattern.subn(lambda m: m.group(1) + version + m.group(2), text)
    if n == 0:
        print(f"错误：{rel} 未命中版本落点（文件结构变了？请同步更新 sync_version.py 的正则）")
        sys.exit(1)
    if n > 1:
        print(f"错误：{rel} 版本落点命中 {n} 处，预期 1 处")
        sys.exit(1)
    return new


def _main() -> int:
    parser = argparse.ArgumentParser(description="VERSION 单一源 → 三处落点同步")
    parser.add_argument("--check", action="store_true", help="只校验一致性，不写入（CI 用）")
    args = parser.parse_args()

    version = read_version()
    drifted: list[str] = []
    for rel, pattern in TARGETS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        new = _replace(text, pattern, version, rel)
        if new == text:
            print(f"OK   {rel} = {version}")
            continue
        drifted.append(rel)
        if args.check:
            print(f"漂移 {rel} ≠ VERSION({version})")
        else:
            path.write_text(new, encoding="utf-8")
            print(f"同步 {rel} → {version}")

    if args.check and drifted:
        print(f"错误：{len(drifted)} 处版本漂移，跑 python3 scripts/sync_version.py 修复")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
