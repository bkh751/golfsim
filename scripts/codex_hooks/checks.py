from __future__ import annotations

import json
import os
import py_compile
import subprocess
from pathlib import Path
from typing import Any, Dict, List

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


FRONTEND_CHECK_FILES = {
    "index.html",
    "swing-model.js",
    "impact-agent.js",
    "flight-engine.js",
    "aero-model.js",
    "metrics-agent.js",
    "fitting-agent.js",
}

ROUND_TRIGGER_FILES = FRONTEND_CHECK_FILES | {
    "index.html",
    "scripts/run-action.mjs",
    "package.json",
    "package-lock.json",
}


def collect_changed_files(repo_root: Path) -> List[str]:
    commands = (
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    changed = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            continue
        changed.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(
        path
        for path in changed
        if "__pycache__/" not in path and not path.endswith(".pyc")
    )


def select_checks(changed_files: List[str]) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    if any(_needs_npm_test(path) for path in changed_files):
        selected.append(
            {
                "id": "npm_test",
                "label": "npm test",
                "kind": "command",
                "command": ["npm", "test"],
            }
        )
    if any(_needs_go_test(path) for path in changed_files):
        selected.append(
            {
                "id": "go_test_orchestrator",
                "label": "go test ./tools/codex-orchestrator-mcp/...",
                "kind": "command",
                "command": ["go", "test", "./..."],
                "cwd": "tools/codex-orchestrator-mcp",
            }
        )
    if any(_needs_codex_config_check(path) for path in changed_files):
        selected.append(
            {
                "id": "codex_config",
                "label": "Codex config/hooks/dashboard smoke",
                "kind": "python",
            }
        )
    return selected


def run_selected_checks(repo_root: Path, selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for check in selected:
        if check["kind"] == "command":
            results.append(_run_command_check(repo_root, check))
        else:
            results.append(_run_python_check(repo_root, check))
    return results


def _run_command_check(repo_root: Path, check: Dict[str, Any]) -> Dict[str, Any]:
    command_cwd = repo_root / check.get("cwd", "")
    result = subprocess.run(
        check["command"],
        cwd=command_cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "id": check["id"],
        "label": check["label"],
        "ok": result.returncode == 0,
        "command": " ".join(check["command"]),
        "cwd": str(command_cwd),
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _run_python_check(repo_root: Path, check: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    try:
        tomllib.loads((repo_root / ".codex" / "config.toml").read_text())
    except Exception as exc:  # noqa: BLE001
        errors.append(f".codex/config.toml parse 실패: {exc}")

    try:
        json.loads((repo_root / ".codex" / "hooks.json").read_text())
    except Exception as exc:  # noqa: BLE001
        errors.append(f".codex/hooks.json parse 실패: {exc}")

    for relative_path in (
        "scripts/codex-hooks/main.py",
        "scripts/codex-harness-dashboard.py",
        "scripts/codex-harness-worker.py",
        "scripts/codex_hooks/app.py",
        "scripts/codex_hooks/classify.py",
        "scripts/codex_hooks/orchestrator_state.py",
        "scripts/codex_hooks/checks.py",
        "scripts/codex_hooks/rounds.py",
        "scripts/codex_harness_dashboard.py",
        "scripts/codex_harness_worker.py",
    ):
        try:
            py_compile.compile(str(repo_root / relative_path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{relative_path} py_compile 실패: {exc.msg}")

    try:
        _dashboard_smoke(repo_root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"dashboard smoke 실패: {exc}")

    return {
        "id": check["id"],
        "label": check["label"],
        "ok": not errors,
        "command": "python config/dashboard smoke",
        "cwd": str(repo_root),
        "stdout": "",
        "stderr": "\n".join(errors),
    }


def _dashboard_smoke(repo_root: Path) -> None:
    required_static = (
        repo_root / "tools" / "codex-harness-dashboard" / "index.html",
        repo_root / "tools" / "codex-harness-dashboard" / "app.js",
        repo_root / "tools" / "codex-harness-dashboard" / "styles.css",
    )
    for path in required_static:
        if not path.exists():
            raise FileNotFoundError(f"정적 자산 누락: {path}")

    from scripts import codex_harness_dashboard

    dashboard = codex_harness_dashboard.build_dashboard_payload(repo_root)
    hooks = codex_harness_dashboard.build_hooks_payload(repo_root)
    team = codex_harness_dashboard.build_team_payload(repo_root, "pm")

    required_dashboard_keys = {"generated_at", "orchestrator", "teams", "hooks", "summary", "worker", "rounds"}
    if not required_dashboard_keys.issubset(dashboard.keys()):
        raise ValueError("dashboard payload key 누락")
    if "last_intake" not in hooks or "last_check" not in hooks:
        raise ValueError("hooks payload key 누락")
    if team.get("role") != "pm":
        raise ValueError("team payload contract 실패")


def should_trigger_roundtable(changed_files: List[str]) -> bool:
    if not changed_files:
        return False
    return any(_is_round_trigger_path(path) for path in changed_files)


def derive_round_topic(changed_files: List[str]) -> str:
    if not changed_files:
        return "변경 파일 없음"
    focus: List[str] = []
    if any(path == "index.html" or path.startswith("test/") for path in changed_files):
        focus.append("UI/플레이 루프")
    if any(path in {"flight-engine.js", "impact-agent.js", "aero-model.js", "swing-model.js", "metrics-agent.js", "fitting-agent.js"} for path in changed_files):
        focus.append("물리/입력")
    if any(path.startswith("tools/codex-harness-dashboard/") or path.startswith("scripts/codex_harness_dashboard") for path in changed_files):
        focus.append("운영 대시보드")
    if not focus:
        focus.append(Path(changed_files[0]).name)
    return ", ".join(dict.fromkeys(focus))


def _needs_npm_test(path: str) -> bool:
    return path in FRONTEND_CHECK_FILES or path.startswith("test/")


def _needs_go_test(path: str) -> bool:
    return path.startswith("tools/codex-orchestrator-mcp/") or path == "scripts/start-codex-orchestrator-mcp.sh"


def _needs_codex_config_check(path: str) -> bool:
    return (
        path in {
            "AGENTS.md",
            ".codex/config.toml",
            ".codex/hooks.json",
            "scripts/codex-harness-dashboard.py",
            "scripts/codex-harness-worker.py",
        }
        or path.startswith("scripts/codex-hooks/")
        or path.startswith("scripts/codex_hooks/")
        or path.startswith("tools/codex-harness-dashboard/")
    )


def _is_round_trigger_path(path: str) -> bool:
    return (
        path in ROUND_TRIGGER_FILES
        or path.startswith("test/")
        or path.startswith("scripts/run-action")
        or path.startswith("scripts/serve")
    )
