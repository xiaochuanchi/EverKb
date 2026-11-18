"""LLM 真实连通性验证（Plan 2 Task 16 Step 3）。

手动执行：`python scripts/verify_llm.py --model doubao-seed-2-0-lite-260428`。
读取 .env 的 ARK_API_KEY / ARK_BASE_URL（火山方舟），先非流式返回一段，
再流式逐片段打印，最后打印 usage 与 PASS。
"""
import argparse
import sys
from pathlib import Path

# 脚本位于仓库根 scripts/，app 包在 backend/ 下：锚定后任意工作目录可执行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.llm import ChatMessage, OpenAICompatibleLLM  # noqa: E402

_DEFAULT_MODEL = "doubao-seed-2-0-lite-260428"


def _main() -> int:
    parser = argparse.ArgumentParser(description="LLM（火山方舟豆包）连通性验证")
    parser.add_argument("--model", default=_DEFAULT_MODEL, help="模型 ID（方舟 Model ID）")
    parser.add_argument("--base-url", default=None, help="覆盖 base_url（默认读 .env ARK_BASE_URL）")
    parser.add_argument("--api-key", default=None, help="覆盖 api_key（默认读 .env ARK_API_KEY）")
    args = parser.parse_args()

    from app.core.config import get_settings

    settings = get_settings()
    base_url = args.base_url or settings.llm_base_url
    api_key = args.api_key or settings.llm_api_key
    if not api_key:
        print("错误：未找到 ARK_API_KEY（请确认 .env 已填，或 --api-key 传入）")
        return 1

    llm = OpenAICompatibleLLM(base_url=base_url, api_key=api_key, model=args.model)
    messages = [ChatMessage(role="user", content="用一句话介绍你自己，不超过 30 字。")]

    # 1) 非流式
    result = llm.chat(messages)
    print(f"[非流式] {result.content}")
    print(f"[usage] in={result.tokens_in} out={result.tokens_out}")

    # 2) 流式
    print("[流式] ", end="", flush=True)
    full = ""
    for chunk in llm.chat_stream(messages):
        full += chunk.delta
        print(chunk.delta, end="", flush=True)
    print()
    assert full.strip(), "流式输出为空"
    print(f"PASS（model={args.model}, base_url={base_url}）")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
