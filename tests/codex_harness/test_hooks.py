from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.codex_hooks.checks import derive_round_topic, select_checks, should_trigger_roundtable
from scripts.codex_hooks.classify import classify_prompt
from scripts.codex_hooks.orchestrator_state import summarize_orchestrator
from scripts.codex_hooks.app import _extract_context_usage_percent, run_hook, to_codex_output


class ClassifyPromptTests(unittest.TestCase):
    def test_issue_and_team_keywords_become_orchestrator_candidate(self) -> None:
        result = classify_prompt("#24 기준으로 PM, 디자인, 개발, 게임플레이 QA 팀 세션을 조율해줘")
        self.assertTrue(result["orchestrator_candidate"])
        self.assertEqual(result["issues"], ["#24"])
        self.assertIn("pm", result["recommended_roles"])
        self.assertIn("design", result["recommended_roles"])
        self.assertIn("dev", result["recommended_roles"])
        self.assertIn("gameplay_qa", result["recommended_roles"])
        self.assertEqual(result["session_mode"], "orchestration")

    def test_team_request_without_issue_needs_parent_issue(self) -> None:
        result = classify_prompt("디자인 팀이랑 개발 팀 세션을 같이 dispatch해줘")
        self.assertTrue(result["needs_parent_issue"])
        self.assertFalse(result["orchestrator_candidate"])
        self.assertEqual(result["session_mode"], "orchestration")

    def test_meta_harness_prompt_is_not_orchestration(self) -> None:
        result = classify_prompt("하네스 dashboard와 hook protocol을 분석하고 AGENTS 규칙을 정리해줘")
        self.assertEqual(result["session_mode"], "meta_harness")
        self.assertFalse(result["orchestrator_candidate"])
        self.assertFalse(result["needs_parent_issue"])


class OrchestratorStateTests(unittest.TestCase):
    def test_stale_parse_error_and_blocking_roles_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".codex" / "orchestrator").mkdir(parents=True)
            (repo / ".codex" / "orchestrator" / "targets.json").write_text(
                json.dumps({"pm": "1", "planning": "2", "design": "3", "gameplay_qa": "4"})
            )
            stale_time = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
            fresh_time = datetime.now(timezone.utc).isoformat()
            (repo / ".codex" / "orchestrator" / "state.json").write_text(
                json.dumps(
                    {
                        "pm": {
                            "thread_title": "PM",
                            "updated_at": fresh_time,
                            "parse_status": "ok",
                            "blocker": "blocker: 없음",
                        },
                        "planning": {
                            "thread_title": "Planning",
                            "updated_at": stale_time,
                            "parse_status": "parse_error",
                            "blocker": "None",
                        },
                        "design": {
                            "thread_title": "Design",
                            "updated_at": fresh_time,
                            "parse_status": "ok",
                            "blocker": "추가 판단 필요",
                        },
                    }
                )
            )
            summary = summarize_orchestrator(repo)
            self.assertFalse(summary["targets_bound"])
            self.assertIn("gameplay_qa", summary["required_roles"])
            self.assertEqual(summary["optional_roles"], [])
            self.assertIn("planning", summary["warm_roles"] + summary["stale_roles"] + summary["critical_roles"])
            self.assertIn("planning", summary["parse_error_roles"])
            self.assertIn("design", summary["blocking_roles"])
            self.assertIn("dev", summary["unbound_required_roles"])


class CheckSelectionTests(unittest.TestCase):
    def test_select_checks_matches_expected_groups(self) -> None:
        checks = select_checks(
            [
                "index.html",
                "tools/codex-orchestrator-mcp/service.go",
                ".codex/config.toml",
                "tools/codex-harness-dashboard/index.html",
            ]
        )
        ids = [item["id"] for item in checks]
        self.assertIn("npm_test", ids)
        self.assertIn("go_test_orchestrator", ids)
        self.assertIn("codex_config", ids)

    def test_round_trigger_detection_uses_gameplay_files(self) -> None:
        self.assertTrue(should_trigger_roundtable(["index.html"]))
        self.assertTrue(should_trigger_roundtable(["test/ui-interaction.test.mjs"]))
        self.assertFalse(should_trigger_roundtable(["docs/product.md"]))
        self.assertIn("UI/플레이 루프", derive_round_topic(["index.html", "test/ui-interaction.test.mjs"]))


class ContextGuardTests(unittest.TestCase):
    def test_context_guard_blocks_when_percent_exceeds_threshold(self) -> None:
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "context_usage_percent": 18.4,
            "session_id": "sess-1",
        }
        result = run_hook("context_guard", "advisory", payload)
        self.assertEqual(result["status"], "block")
        self.assertEqual(result["context_usage_percent"], 18.4)
        codex_output = to_codex_output(result, payload)
        self.assertEqual(codex_output["decision"], "block")

    def test_context_guard_detects_nested_usage_window(self) -> None:
        payload = {
            "usage": {
                "context_window": {
                    "used_tokens": 120,
                    "max_tokens": 1000,
                }
            }
        }
        percent, source = _extract_context_usage_percent(payload)
        self.assertEqual(percent, 12.0)
        self.assertEqual(source, "usage.context_window")

    def test_context_guard_allows_when_usage_field_missing(self) -> None:
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "간단한 분석",
        }
        result = run_hook("context_guard", "advisory", payload)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["context_detected"])


if __name__ == "__main__":
    unittest.main()
