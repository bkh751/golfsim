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

from scripts.codex_hooks.repair_queue import (
    approve_repair_item,
    load_repair_queue,
    mark_repair_done,
    mark_repair_running,
    save_repair_queue,
)
from scripts.codex_harness_worker import (
    _build_adaptive_prompt,
    _is_stale_running_round,
    _local_role_result,
    _parse_harness_final_json,
    _route_progress_has_activity,
    _timeout_fallback_kind,
)
from scripts.codex_hooks.rounds import create_round_request, list_rounds, sanitize_round_artifacts


class RoundQueueTests(unittest.TestCase):
    def test_round_request_dedupes_pending_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            round_one, dedupe_one = create_round_request(
                repo,
                issue_ref="#24",
                trigger="stop_hook",
                changed_files=["index.html", "test/ui-interaction.test.mjs"],
                topic="UI/플레이 루프",
            )
            round_two, dedupe_two = create_round_request(
                repo,
                issue_ref="#24",
                trigger="stop_hook",
                changed_files=["test/ui-interaction.test.mjs", "index.html"],
                topic="UI/플레이 루프",
            )
            rounds = list_rounds(repo)

            self.assertFalse(dedupe_one)
            self.assertTrue(dedupe_two)
            self.assertEqual(round_one["id"], round_two["id"])
            self.assertEqual(len(rounds), 1)
            self.assertIn("gameplay_qa", round_one["required_roles"])
            self.assertEqual(round_one["optional_roles"], [])

    def test_sanitize_round_artifacts_removes_blank_time_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            round_one, _ = create_round_request(
                repo,
                issue_ref="#19",
                trigger="manual",
                changed_files=["index.html"],
                topic="퍼터 세션",
            )
            round_path = repo / ".codex" / "harness" / "rounds" / f"{round_one['id']}.json"
            payload = json.loads(round_path.read_text())
            payload["started_at"] = ""
            payload["completed_at"] = ""
            round_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

            updated = sanitize_round_artifacts(repo)
            rounds = list_rounds(repo)

            self.assertEqual(updated, 1)
            self.assertNotIn("started_at", rounds[0])
            self.assertNotIn("completed_at", rounds[0])


class WorkerHelperTests(unittest.TestCase):
    def test_repair_queue_state_transitions_follow_pending_to_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            now = datetime.now(timezone.utc).isoformat()
            save_repair_queue(
                repo,
                [
                    {
                        "id": "repair-1",
                        "kind": "stale_sync",
                        "priority": 1,
                        "title": "planning stale sync",
                        "reason": "planning stale",
                        "target_role": "planning",
                        "action": "sync_role_state",
                        "auto_executable": True,
                        "requires_approval": True,
                        "status": "pending",
                        "created_at": now,
                        "updated_at": now,
                        "dedupe_key": "stale_sync::planning::-::-",
                    }
                ],
            )

            approved = approve_repair_item(repo, "repair-1")
            running = mark_repair_running(repo, "repair-1")
            done = mark_repair_done(repo, "repair-1", "sync ok")
            loaded = load_repair_queue(repo)[0]

            self.assertEqual(approved["status"], "approved")
            self.assertEqual(running["status"], "running")
            self.assertEqual(done["status"], "done")
            self.assertEqual(loaded["last_note"], "sync ok")

    def test_parse_harness_final_json_extracts_embedded_payload(self) -> None:
        raw = """
상태: 완료
이해한 범위: 테스트
결과: 아래 JSON 참고
blocker: 없음
다음 요청: 없음

```json
{"round_summary":"요약","retrospective":"회고","gameplay_findings":["a"],"backlog_candidates":[{"title":"후속","summary":"설명","team_label":"planning","acceptance_criteria":["x"]}]}
```
"""
        payload = _parse_harness_final_json(raw)
        self.assertEqual(payload["round_summary"], "요약")
        self.assertEqual(payload["backlog_candidates"][0]["team_label"], "planning")

    def test_local_pm_final_fallback_contains_json_payload(self) -> None:
        result = _local_role_result(
            "pm",
            "PM 최종 회고 및 백로그 합성",
            {"issue_ref": "#24", "topic": "UI/플레이 루프"},
            {"ok": True, "render_payload": {"cameraMode": "follow"}},
            [
                {
                    "role": "gameplay_qa",
                    "result": "자동 플레이 기준으로 반복 플레이 감이 유지된다.",
                }
            ],
            reason="dispatch timeout 60s",
        )
        payload = _parse_harness_final_json(result["raw"])
        self.assertEqual(result["status"], "로컬 pm 최종 fallback")
        self.assertEqual(payload["backlog_candidates"], [])
        self.assertIn("즉시 수정", result["result"])

    def test_stale_running_round_is_recoverable_when_worker_is_dead(self) -> None:
        round_payload = {
            "id": "round-1",
            "status": "running",
            "updated_at": "2026-04-10T05:00:00+00:00",
        }
        worker_status = {
            "current_round_id": "round-1",
            "pid": 999999,
        }
        self.assertTrue(_is_stale_running_round(round_payload, worker_status))

    def test_timeout_fallback_kind_demotes_downstream_steps(self) -> None:
        self.assertEqual(_timeout_fallback_kind([]), "timeout_fallback")
        self.assertEqual(
            _timeout_fallback_kind([{"fallback_kind": "timeout_fallback"}]),
            "upstream_timeout",
        )

    def test_route_progress_activity_requires_recent_stream(self) -> None:
        recent = datetime.now(timezone.utc).isoformat()
        stale = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()

        self.assertTrue(
            _route_progress_has_activity(
                {"progress_state": "ack", "last_stream_at": recent},
                30,
            )
        )
        self.assertFalse(
            _route_progress_has_activity(
                {"progress_state": "ack", "last_stream_at": stale},
                30,
            )
        )

    def test_adaptive_prompt_requests_compact_ack_first(self) -> None:
        prompt = _build_adaptive_prompt("기존 본문", 15)
        self.assertIn("st:ack | eta:90 | more:1", prompt)
        self.assertIn("기존 본문", prompt)


if __name__ == "__main__":
    unittest.main()
