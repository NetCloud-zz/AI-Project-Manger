"""CLI: ``python -m app.evals --mode intent --intent-mode both --repeat 3``.

Intent mode never writes. Agent mode runs full conversations in disposable
SQLite (default) or a throwaway PostgreSQL schema (``--database-url app``).
Live-model runs cost tokens; results go to ``evals/results/`` (not committed).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.evals.cases import load_cases, repair_fixture_cases
from app.evals.runner import (
    RunResult,
    run_agent_suite,
    run_intent_suite,
    summarize,
    to_jsonable,
)

EVAL_DIR = Path(__file__).resolve().parents[2] / "evals"
DEFAULT_CASES = [EVAL_DIR / "assistant_core.yaml", EVAL_DIR / "cases.yaml"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.evals", description=__doc__)
    parser.add_argument("--mode", choices=["intent", "agent"], default="intent")
    parser.add_argument("--cases", type=Path, action="append", help="YAML case file(s)")
    parser.add_argument("--only", action="append", default=[], help="case id or tag filter")
    parser.add_argument("--intent-mode", choices=["regex", "hybrid", "both"], default="both")
    parser.add_argument("--toolsets", choices=["on", "off", "both"], default="on")
    parser.add_argument("--runtime", choices=["agentscope", "legacy"], default=None)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--database-url",
        default=None,
        help="'app' = throwaway schema on DATABASE_URL; omit for in-memory SQLite",
    )
    parser.add_argument("--include-repair24", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    return parser


def _variants(args: argparse.Namespace) -> list[tuple[str, dict[str, object]]]:
    intents = ["regex", "hybrid"] if args.intent_mode == "both" else [args.intent_mode]
    toolsets = (
        [("on", True), ("off", False)]
        if args.toolsets == "both"
        else [(args.toolsets, args.toolsets == "on")]
    )
    variants = []
    for intent in intents:
        if args.mode == "intent":
            variants.append((intent, {"AGENT_INTENT_MODE": intent}))
            continue
        for label, enabled in toolsets:
            update: dict[str, object] = {
                "AGENT_INTENT_MODE": intent,
                "AGENT_TOOLSETS_ENABLED": enabled,
                "AGENT_TRACE_LOG": False,
            }
            if args.runtime:
                update["AGENT_RUNTIME"] = args.runtime
            variants.append((f"{intent}/toolsets-{label}", update))
    return variants


def _print_progress(result: RunResult) -> None:
    mark = "PASS" if result.passed else "FAIL"
    detail = "" if result.passed else " — " + "; ".join(result.failures)
    print(f"[{result.variant}] {result.case_id} #{result.repeat}: {mark}{detail}", flush=True)


async def _main(args: argparse.Namespace) -> int:
    base = get_settings()
    cases = [c for c in load_cases(args.cases or DEFAULT_CASES) if args.mode in c.modes]
    if args.include_repair24 and args.mode == "agent":
        cases += repair_fixture_cases(EVAL_DIR / "assistant_repair_24x1.yaml")
    if args.only:
        wanted = set(args.only)
        cases = [c for c in cases if c.id in wanted or wanted & set(c.tags)]
    if not cases:
        print("No cases selected.", file=sys.stderr)
        return 2
    database_url = base.DATABASE_URL if args.database_url == "app" else args.database_url

    results: list[RunResult] = []
    for variant, update in _variants(args):
        settings = base.model_copy(update=update)
        if args.mode == "intent":
            from app.llm.gateway import create_llm_gateway

            rows = await run_intent_suite(
                cases,
                settings=settings,
                gateway=create_llm_gateway(settings),
                variant=variant,
                repeat=args.repeat,
            )
            for row in rows:
                _print_progress(row)
        else:
            rows = await run_agent_suite(
                cases,
                settings=settings,
                database_url=database_url,
                variant=variant,
                repeat=args.repeat,
                on_result=_print_progress,
            )
        results += rows

    summary = summarize(results)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": args.mode,
        "model_reasoning": base.LLM_MODEL_REASONING,
        "model_fast": base.LLM_MODEL_FAST,
        "cases": len(cases),
        "repeat": args.repeat,
        "summary": summary,
        "results": to_jsonable(results),
    }
    out = args.out or EVAL_DIR / "results" / (
        f"{args.mode}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("\n| variant | runs | pass rate | unsafe | missed/avg tools | avg ms |")
    print("| --- | --- | --- | --- | --- | --- |")
    for key, entry in summary.items():
        extra = entry.get("missed", entry.get("avg_tool_calls"))
        print(
            f"| {key} | {entry['runs']} | {entry['pass_rate']:.0%} | {entry['unsafe']} | "
            f"{extra} | {entry['avg_duration_ms']} |"
        )
    print(f"\nReport: {out}")
    return 0 if all(entry["unsafe"] == 0 for entry in summary.values()) else 1


def main() -> None:
    raise SystemExit(asyncio.run(_main(_parser().parse_args())))


if __name__ == "__main__":
    main()
