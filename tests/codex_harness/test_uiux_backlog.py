from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.codex_hooks.uiux_backlog import (  # noqa: E402
    build_reference_digest,
    load_design_backlog,
    normalize_design_backlog_item,
    reference_snapshot_dir,
    save_design_backlog,
)


class UiuxBacklogTests(unittest.TestCase):
    def test_reference_digest_contains_required_axes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            snapshot = reference_snapshot_dir(repo)
            snapshot.mkdir(parents=True)
            (snapshot / "README.md").write_text("# ref\nExecutive Dashboard\n", encoding="utf-8")
            (snapshot / "CLAUDE.md").write_text("style\nanti-pattern\n", encoding="utf-8")

            digest = build_reference_digest(repo)

            self.assertIn("dashboard_pattern", digest)
            self.assertIn("visual_style", digest)
            self.assertIn("anti_patterns", digest)
            self.assertIn("checklist", digest)
            self.assertEqual(digest["reference_mode"], "snapshot")

    def test_normalize_design_backlog_item_fills_defaults(self) -> None:
        spec = {
            "iteration": 3,
            "layer": "abstract",
            "title": "추상화 탭 후보와 게이트 조건 정의",
            "tab_target": "abstract",
            "screen_target": "abstract-tab-candidate",
            "trigger_state": "cross_tab_synthesis_needed",
            "default_problem": "문제",
            "default_proposal": "제안",
            "default_anti_patterns": ["중복 탭"],
            "default_acceptance_hint": "수용 기준",
            "default_priority": "follow-up",
            "default_status": "follow-up",
            "default_owner": "pm",
        }

        item = normalize_design_backlog_item({"title": "임시"}, spec)

        self.assertEqual(item["title"], "임시")
        self.assertEqual(item["status"], "follow-up")
        self.assertEqual(item["priority"], "follow-up")
        self.assertEqual(item["reference_basis"][0], "Executive Dashboard")

    def test_load_design_backlog_returns_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            payload = {
                "generated_at": "2026-04-11T00:00:00+00:00",
                "reference_mode": "snapshot",
                "reference_digest_summary": {"reference_mode": "snapshot"},
                "orchestration": {"iterations_completed": 15},
                "items": [
                    {
                        "id": "uiux-01",
                        "iteration": 1,
                        "layer": "abstract",
                        "title": "item",
                        "tab_target": "overview",
                        "screen_target": "hero",
                        "trigger_state": "dashboard_load",
                        "problem": "p",
                        "proposal": "q",
                        "reference_basis": ["Executive Dashboard"],
                        "anti_patterns": ["중복"],
                        "acceptance_hint": "ok",
                        "priority": "immediate",
                        "status": "priority",
                        "owner": "pm",
                        "source_round_id": "uiux-iteration-01",
                    }
                ],
                "iteration_rationale": [],
            }
            save_design_backlog(repo, payload)

            loaded = load_design_backlog(repo)

            self.assertEqual(loaded["counts"]["total"], 1)
            self.assertEqual(loaded["counts"]["priority"], 1)


if __name__ == "__main__":
    unittest.main()
