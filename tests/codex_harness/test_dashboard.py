from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.codex_harness_dashboard import (
    DashboardHandler,
    build_dashboard_payload,
    build_hooks_payload,
    build_team_payload,
)


class DashboardPayloadTests(unittest.TestCase):
    def test_dashboard_contract_uses_file_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".codex" / "orchestrator").mkdir(parents=True)
            (repo / ".codex" / "harness" / "logs").mkdir(parents=True)
            (repo / ".codex" / "harness" / "rounds").mkdir(parents=True)
            (repo / ".codex" / "harness" / "reference").mkdir(parents=True)
            stale_time = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
            fresh_time = datetime.now(timezone.utc).isoformat()

            (repo / ".codex" / "orchestrator" / "targets.json").write_text(json.dumps({"pm": "1"}))
            (repo / ".codex" / "orchestrator" / "state.json").write_text(
                json.dumps(
                    {
                        "pm": {
                            "thread_title": "PM",
                            "updated_at": fresh_time,
                            "parse_status": "ok",
                            "blocker": "blocker: 없음",
                            "last_stream_at": fresh_time,
                            "declared_eta_seconds": 90,
                            "progress_state": "work",
                        },
                        "planning": {
                            "thread_title": "Planning",
                            "updated_at": stale_time,
                            "parse_status": "parse_error",
                            "blocker": "None",
                        },
                        "gameplay_qa": {
                            "thread_title": "Gameplay QA",
                            "updated_at": fresh_time,
                            "parse_status": "ok",
                            "blocker": "blocker: 없음",
                        },
                    }
                )
            )
            (repo / ".codex" / "harness" / "last-intake.json").write_text(
                json.dumps({"status": "warn", "summary": "input warn", "details": [], "next_action": "fix"})
            )
            (repo / ".codex" / "harness" / "last-orchestrator-hint.json").write_text(
                json.dumps({"status": "ok", "summary": "hint ok", "details": [], "next_action": "none"})
            )
            (repo / ".codex" / "harness" / "last-check.json").write_text(
                json.dumps({"status": "block", "summary": "check blocked", "details": ["[fail] npm test"], "next_action": "run tests"})
            )
            (repo / ".codex" / "harness" / "worker-status.json").write_text(
                json.dumps({"state": "idle", "updated_at": fresh_time, "pending_rounds": 1})
            )
            qa_dir = repo / ".codex" / "harness" / "qa-evidence"
            qa_dir.mkdir(parents=True, exist_ok=True)
            historical_failure = qa_dir / "round-old.json"
            historical_failure.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "stderr": "page.evaluate: TypeError: window.render_game_to_text is not a function",
                    }
                )
            )
            (repo / ".codex" / "harness" / "rounds" / "round-1.json").write_text(
                json.dumps(
                    {
                        "id": "round-1",
                        "status": "completed",
                        "created_at": fresh_time,
                        "updated_at": fresh_time,
                        "participants": ["pm", "planning", "design", "dev", "gameplay_qa"],
                        "summary": "round ok",
                        "retrospective": "retro ok",
                        "steps": [
                            {
                                "stage": "pm_frame",
                                "role": "pm",
                                "parse_status": "ok",
                                "thread_id": "thread-pm",
                                "result": "pm result",
                            },
                            {
                                "stage": "design_rebuttal",
                                "role": "design",
                                "parse_status": "fallback",
                                "fallback_kind": "timeout_fallback",
                                "timeout_reason": "no_heartbeat",
                                "eta_seconds": 90,
                                "progress_state": "work",
                                "last_stream_at": fresh_time,
                                "adaptive_deadline": fresh_time,
                                "extended_slices": 2,
                                "thread_id": "local-fallback",
                                "result": "design result",
                            },
                        ],
                        "gameplay_findings": ["flight info is readable"],
                        "issue_draft_results": [{"title": "draft", "status": "created"}],
                    }
                )
            )
            prompt_dir = repo / ".codex" / "orchestrator" / "prompts"
            prompt_dir.mkdir(parents=True)
            prompt_path = prompt_dir / "20260410T090000-pm.md"
            prompt_path.write_text("pm prompt body with compact summary")
            (repo / ".codex" / "orchestrator" / "dispatches.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "event": "started",
                                "dispatch_id": "pm-1",
                                "role": "pm",
                                "thread_title": "PM",
                                "created_at": fresh_time,
                                "prompt_path": str(prompt_path),
                            }
                        ),
                        json.dumps(
                            {
                                "event": "completed",
                                "dispatch_id": "pm-1",
                                "role": "pm",
                                "thread_title": "PM",
                                "completed_at": fresh_time,
                            }
                        ),
                    ]
                )
                + "\n"
            )
            (repo / ".codex" / "harness" / "reference" / "ui-ux-dashboard-digest.json").write_text(
                json.dumps(
                    {
                        "reference_mode": "snapshot",
                        "dashboard_pattern": ["Executive Dashboard", "Real-Time Monitoring", "Comparative Analysis Dashboard"],
                        "visual_style": ["Dimensional Layering", "Minimalism & Swiss Style"],
                        "chart_style": ["Comparative analysis", "Status density"],
                        "anti_patterns": ["ornate design", "AI purple/pink gradients"],
                        "checklist": ["prefers-reduced-motion respected", "keyboard navigation"],
                        "motion_rules": ["150-250ms transitions"],
                        "typography_rules": ["14-16px minimum body size"],
                        "sources": ["README.md", "CLAUDE.md"],
                    }
                )
            )
            (repo / ".codex" / "harness" / "design-backlog.json").write_text(
                json.dumps(
                    {
                        "generated_at": fresh_time,
                        "reference_mode": "snapshot",
                        "reference_digest_summary": {
                            "reference_mode": "snapshot",
                            "pattern": "Executive Dashboard · Real-Time Monitoring · Comparative Analysis Dashboard",
                            "style": "Dimensional Layering · Minimalism & Swiss Style",
                            "chart": "Comparative analysis · Status density",
                            "anti_patterns": ["ornate design"],
                            "checklist": ["prefers-reduced-motion respected"],
                            "source_count": 2,
                        },
                        "orchestration": {
                            "iterations_requested": 15,
                            "iterations_completed": 15,
                            "execution_mode": "fallback_synthesis",
                            "participants": ["pm", "planning", "design"],
                        },
                        "items": [
                            {
                                "id": "uiux-01",
                                "iteration": 1,
                                "layer": "abstract",
                                "title": "운영자 미션 스트립과 핵심 과업 3개 고정",
                                "tab_target": "overview",
                                "screen_target": "overview-hero",
                                "trigger_state": "dashboard_load",
                                "problem": "문제",
                                "proposal": "제안",
                                "reference_basis": ["Executive Dashboard"],
                                "anti_patterns": ["ornate design"],
                                "acceptance_hint": "수용 기준",
                                "priority": "immediate",
                                "status": "priority",
                                "owner": "pm",
                                "source_round_id": "uiux-iteration-01",
                            }
                        ],
                        "iteration_rationale": [
                            {
                                "iteration": 1,
                                "topic": "운영 사용자의 핵심 과업과 mental model을 정의한다.",
                                "mode": "fallback_synthesis",
                                "planning": "planning note",
                                "design": "design note",
                                "pm": "pm note",
                                "source_round_id": "uiux-iteration-01",
                            }
                        ],
                        "abstract_gate": {
                            "candidate_allowed": False,
                            "signals": {
                                "unique_info_layer": False,
                                "unique_action_purpose": False,
                                "low_overview_overlap": True,
                            },
                        },
                    }
                )
            )

            dashboard = build_dashboard_payload(repo)
            hooks = build_hooks_payload(repo)
            team = build_team_payload(repo, "pm")

            self.assertIn("generated_at", dashboard)
            self.assertIn("orchestrator", dashboard)
            self.assertIn("worker", dashboard)
            self.assertIn("rounds", dashboard)
            self.assertIn("interaction_health", dashboard)
            self.assertIn("effectiveness", dashboard)
            self.assertIn("harness_efficiency", dashboard)
            self.assertIn("repair_queue", dashboard)
            self.assertIn("synthesis", dashboard)
            self.assertIn("routing_graph", dashboard)
            self.assertIn("qa_observation", dashboard)
            self.assertIn("design_backlog", dashboard)
            self.assertIn("reference_digest_summary", dashboard)
            self.assertFalse(dashboard["orchestrator"]["targets_bound"])
            self.assertGreater(dashboard["summary"]["warnings"], 0)
            self.assertGreater(dashboard["summary"]["blocks"], 0)
            self.assertEqual(hooks["last_check"]["status"], "block")
            self.assertEqual(team["role"], "pm")
            self.assertEqual(dashboard["gameplay_findings"], ["flight info is readable"])
            self.assertEqual(dashboard["interaction_health"]["dispatch"]["success_rate"], 100.0)
            self.assertEqual(dashboard["interaction_health"]["relay_prompts"]["coverage_rate"], 20.0)
            self.assertEqual(dashboard["interaction_health"]["latest_round"]["fallback_steps"], 1)
            self.assertIn("gameplay_qa", dashboard["interaction_health"]["unbound_required_roles"])
            self.assertEqual(dashboard["repair_queue"]["items"][0]["kind"], "required_bind_missing")
            self.assertEqual(dashboard["repair_queue"]["items"][-1]["kind"], "fallback_hotspot_review")
            self.assertTrue(dashboard["synthesis"]["turns"])
            self.assertIn("score", dashboard["effectiveness"])
            self.assertEqual(dashboard["routing_graph"]["history"]["dispatch"][0]["source"], "orchestrator")
            self.assertEqual(dashboard["routing_graph"]["history"]["dispatch"][0]["target"], "pm")
            self.assertIn("pm prompt body", dashboard["routing_graph"]["history"]["dispatch"][0]["prompt_preview"])
            self.assertEqual(dashboard["routing_graph"]["history"]["roundtable"][0]["target"], "pm")
            self.assertEqual(dashboard["teams"][0]["declared_eta_seconds"], 90)
            self.assertEqual(dashboard["teams"][0]["progress_state"], "work")
            self.assertIn("timeout_fallback_steps", dashboard["harness_efficiency"]["trend"])
            self.assertEqual(dashboard["qa_observation"]["status"], "follow_up")
            self.assertTrue(dashboard["qa_observation"]["follow_up_recommended"])
            self.assertEqual(dashboard["follow_up_items"][0]["title"], "QA 관측 표면 안정화")
            self.assertEqual(dashboard["design_backlog"]["counts"]["total"], 1)
            self.assertEqual(dashboard["design_backlog"]["orchestration"]["iterations_completed"], 15)
            self.assertEqual(dashboard["reference_digest_summary"]["reference_mode"], "snapshot")
            self.assertEqual(dashboard["design_backlog"]["iteration_rationale"][0]["topic"], "운영 사용자의 핵심 과업과 mental model을 정의한다.")

    def test_repair_queue_priority_orders_stale_parse_dispatch_and_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".codex" / "orchestrator").mkdir(parents=True)
            (repo / ".codex" / "harness" / "logs").mkdir(parents=True)
            (repo / ".codex" / "harness" / "rounds").mkdir(parents=True)
            stale_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
            fresh_time = datetime.now(timezone.utc).isoformat()

            (repo / ".codex" / "orchestrator" / "targets.json").write_text(
                json.dumps({role: f"thread-{role}" for role in ("pm", "planning", "design", "dev", "gameplay_qa")})
            )
            (repo / ".codex" / "orchestrator" / "state.json").write_text(
                json.dumps(
                    {
                        "pm": {"thread_title": "PM", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                        "planning": {"thread_title": "Planning", "updated_at": stale_time, "parse_status": "ok", "blocker": "없음"},
                        "design": {"thread_title": "Design", "updated_at": fresh_time, "parse_status": "parse_error", "blocker": "없음"},
                        "dev": {"thread_title": "Dev", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                        "gameplay_qa": {"thread_title": "Gameplay QA", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                    }
                )
            )
            (repo / ".codex" / "harness" / "worker-status.json").write_text(
                json.dumps({"state": "idle", "updated_at": fresh_time, "pending_rounds": 0})
            )
            (repo / ".codex" / "harness" / "rounds" / "round-1.json").write_text(
                json.dumps(
                    {
                        "id": "round-1",
                        "status": "completed",
                        "created_at": fresh_time,
                        "updated_at": fresh_time,
                        "summary": "round ok",
                        "retrospective": "retro ok",
                        "steps": [
                            {"stage": "pm_frame", "role": "pm", "parse_status": "ok", "thread_id": "thread-pm", "result": "pm result"},
                            {"stage": "design_peer", "role": "design", "parse_status": "fallback", "thread_id": "local-fallback", "result": "fallback"},
                            {"stage": "dev_peer", "role": "dev", "parse_status": "fallback", "thread_id": "local-fallback", "result": "fallback"},
                        ],
                    }
                )
            )
            (repo / ".codex" / "orchestrator" / "dispatches.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"event": "started", "dispatch_id": "dev-open", "role": "dev", "thread_title": "Dev", "created_at": fresh_time}),
                        json.dumps({"event": "started", "dispatch_id": "pm-done", "role": "pm", "thread_title": "PM", "created_at": fresh_time}),
                        json.dumps({"event": "completed", "dispatch_id": "pm-done", "role": "pm", "thread_title": "PM", "completed_at": fresh_time}),
                    ]
                )
                + "\n"
            )

            dashboard = build_dashboard_payload(repo)
            kinds = [item["kind"] for item in dashboard["repair_queue"]["items"][:4]]

            self.assertEqual(
                kinds,
                ["stale_sync", "parse_repair", "dispatch_retry", "fallback_hotspot_review"],
            )

    def test_historical_render_blocker_is_downgraded_to_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".codex" / "orchestrator").mkdir(parents=True)
            (repo / ".codex" / "harness" / "logs").mkdir(parents=True)
            (repo / ".codex" / "harness" / "rounds").mkdir(parents=True)
            (repo / ".codex" / "harness" / "qa-evidence").mkdir(parents=True)
            fresh_time = datetime.now(timezone.utc).isoformat()

            (repo / ".codex" / "orchestrator" / "targets.json").write_text(
                json.dumps({role: f"thread-{role}" for role in ("pm", "planning", "design", "dev", "gameplay_qa")})
            )
            (repo / ".codex" / "orchestrator" / "state.json").write_text(
                json.dumps(
                    {
                        "pm": {"thread_title": "PM", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                        "planning": {
                            "thread_title": "Planning",
                            "updated_at": fresh_time,
                            "parse_status": "partial",
                            "blocker": "검증선 없이 상태 전이를 확정하기 어렵다.",
                            "raw_final_text": "ev:auto-play fail:`window.render_game_to_text is not a function`",
                        },
                        "design": {"thread_title": "Design", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                        "dev": {
                            "thread_title": "Dev",
                            "updated_at": fresh_time,
                            "parse_status": "relaxed",
                            "blocker": "최소 검증 실패 지속: `window.render_game_to_text is not a function`",
                            "next_request": "`render_game_to_text` 복구",
                        },
                        "gameplay_qa": {"thread_title": "Gameplay QA", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                    }
                )
            )
            (repo / ".codex" / "harness" / "last-check.json").write_text(
                json.dumps(
                    {
                        "status": "block",
                        "summary": "최소 검증 실패",
                        "details": ["[fail] npm test", "putter session display mismatch"],
                        "next_action": "퍼터 세션 회귀 수정",
                        "timestamp": fresh_time,
                    }
                )
            )
            (repo / ".codex" / "harness" / "qa-evidence" / "round-old.json").write_text(
                json.dumps(
                    {
                        "ok": False,
                        "stderr": "page.evaluate: TypeError: window.render_game_to_text is not a function",
                    }
                )
            )
            (repo / ".codex" / "harness" / "worker-status.json").write_text(json.dumps({"state": "idle", "updated_at": fresh_time}))
            (repo / ".codex" / "harness" / "rounds" / "round-1.json").write_text(
                json.dumps({"id": "round-1", "status": "completed", "created_at": fresh_time, "updated_at": fresh_time, "steps": []})
            )

            dashboard = build_dashboard_payload(repo)
            self.assertEqual(dashboard["qa_observation"]["status"], "follow_up")
            self.assertNotIn("dev", dashboard["interaction_health"]["blocking_roles"])
            self.assertEqual(dashboard["teams"][3]["risk_state"], "review")
            self.assertEqual(dashboard["teams"][3]["blocker"], "")
            self.assertEqual(dashboard["follow_up_items"][0]["status"], "follow-up")

    def test_repair_queue_api_approve_and_manual_required_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".codex" / "orchestrator").mkdir(parents=True)
            (repo / ".codex" / "harness" / "logs").mkdir(parents=True)
            (repo / ".codex" / "harness" / "rounds").mkdir(parents=True)
            fresh_time = datetime.now(timezone.utc).isoformat()
            stale_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()

            (repo / ".codex" / "orchestrator" / "targets.json").write_text(
                json.dumps({"pm": "thread-pm", "planning": "thread-planning", "design": "thread-design", "dev": "thread-dev"})
            )
            (repo / ".codex" / "orchestrator" / "state.json").write_text(
                json.dumps(
                    {
                        "pm": {"thread_title": "PM", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                        "planning": {"thread_title": "Planning", "updated_at": stale_time, "parse_status": "ok", "blocker": "없음"},
                        "design": {"thread_title": "Design", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                        "dev": {"thread_title": "Dev", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                        "gameplay_qa": {"thread_title": "Gameplay QA", "updated_at": fresh_time, "parse_status": "ok", "blocker": "없음"},
                    }
                )
            )
            (repo / ".codex" / "harness" / "worker-status.json").write_text(json.dumps({"state": "idle", "updated_at": fresh_time}))
            (repo / ".codex" / "harness" / "rounds" / "round-1.json").write_text(
                json.dumps({"id": "round-1", "status": "completed", "created_at": fresh_time, "updated_at": fresh_time, "steps": []})
            )

            def handler(*args, **kwargs):
                return DashboardHandler(*args, repo_root=repo, **kwargs)

            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                dashboard = json.loads(urlrequest.urlopen(f"{base}/api/dashboard").read().decode("utf-8"))
                stale_item = next(item for item in dashboard["repair_queue"]["items"] if item["kind"] == "stale_sync")
                manual_item = next(item for item in dashboard["repair_queue"]["items"] if item["kind"] == "required_bind_missing")

                approve_request = urlrequest.Request(
                    f"{base}/api/repair-queue/{stale_item['id']}/approve",
                    data=b"",
                    method="POST",
                )
                approved_payload = json.loads(urlrequest.urlopen(approve_request).read().decode("utf-8"))
                self.assertEqual(approved_payload["item"]["status"], "approved")

                manual_request = urlrequest.Request(
                    f"{base}/api/repair-queue/{manual_item['id']}/approve",
                    data=b"",
                    method="POST",
                )
                with self.assertRaises(urlerror.HTTPError) as context:
                    urlrequest.urlopen(manual_request)
                self.assertEqual(context.exception.code, 409)

                enqueue_request = urlrequest.Request(
                    f"{base}/api/repair-queue/enqueue",
                    data=json.dumps(
                        {
                            "title": "weak-point 1",
                            "reason": "최근 round는 완주됐지만 대부분 local fallback으로 채워져 실제 peer-to-peer 품질은 낮다.",
                            "source": "weak-point",
                        }
                    ).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                enqueue_payload = json.loads(urlrequest.urlopen(enqueue_request).read().decode("utf-8"))
                self.assertEqual(enqueue_payload["item"]["kind"], "manual_improvement")
                self.assertEqual(enqueue_payload["item"]["status"], "pending")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
