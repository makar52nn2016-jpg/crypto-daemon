"""
trudyagi/core/demo_llm.py — Mock LLM for demo mode (no API key needed)

Returns canned responses that simulate each role's output.
Useful for:
    - Testing the orchestrator pipeline locally
    - Demonstrating the system to users
    - CI/CD tests without LLM API costs

Demo responses are role-specific and goal-aware (basic pattern matching).
"""

from typing import Literal

# Role names for type hints
Role = Literal["brigadir", "master", "operator", "controller"]


class DemoLLMClient:
    """Mock LLM client — returns canned but context-aware responses."""

    def __init__(self, *args, **kwargs):
        # Ignore all init args (api_key, base_url, model, etc.)
        pass

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Route to role-specific demo responder based on the H1 title
        (first '# Роль' line) of the system_prompt.

        We can't just check 'in system_prompt' because each role's prompt
        references the other roles (e.g. master.md says 'Бригадир дал тебе
        подзадачу'), which would cause false matches.
        """
        # Parse the H1 header (first line starting with '# ')
        first_h1 = ""
        for line in system_prompt.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                first_h1 = line[2:].strip()
                break

        # Match on H1 title (exact match, not substring)
        if first_h1 == "Бригадир":
            return self._brigadir_response(user_prompt)
        if first_h1 == "Мастер":
            return self._master_response(user_prompt)
        if first_h1 == "Контролёр":
            return self._controller_response(user_prompt)
        if first_h1 == "Оператор":
            return self._operator_response(user_prompt)
        # Fallback generic response
        return f"# Demo response\n\nNo H1 found in system prompt.\nFirst 100 chars:\n```\n{system_prompt[:100]}\n```\n\nUser prompt: {user_prompt[:200]}"

    def is_alive(self) -> bool:
        """Demo mode is always alive."""
        return True

    # ---- Role-specific responders ----

    def _brigadir_response(self, user_prompt: str) -> str:
        """Бригадир: parse goal → subtasks. Goal-aware."""
        p = user_prompt.lower()
        if "$1.50" in p or "1.5" in p or "stompstart" in p or "frantic" in p:
            return """```yaml
goal: Earn $1.50 USDC today via Frantic #136 (Stompstart startup listing)
success_criteria:
  - One merged PR on auscaster/stompstart-startup-list adding a new startup
  - Frantic #136 claim status=ACCEPTED after publication gate
  - USDC balance increased by ≥$1.50 on Base wallet
subtasks:
  - id: st-1
    description: Pick a recently launched startup (<6 months) not yet on Stompstart, create proper YAML with logo + product image
    assignee: master
  - id: st-2
    description: Verify Frantic #136 preflight passes (pr_url + website_url + logo_url all bound correctly)
    assignee: controller
notes: PR #9 AgentBounties already in flight — alternative path if Stompstart PR #9 merges first
```"""
        if "lesson" in p or "misakanet" in p:
            return """```yaml
goal: Complete MisakaNet lesson bounty to earn leaderboard credit
success_criteria:
  - One merged PR on Ikalus1988/MisakaNet adding lessons/en/<slug>.md
  - CI all green (lesson_gate, provenance, tests)
  - DCO Signed-off-by trailer present
subtasks:
  - id: st-1
    description: Identify an unanswered MisakaNet question bounty, write lesson that closes it
    assignee: master
  - id: st-2
    description: Verify CI passes + DCO trailer present + derived artifacts regenerated
    assignee: controller
notes: Lesson bounty is $0 by default but unlocks future private bounties via reputation
```"""
        # Generic fallback
        return f"""```yaml
goal: {user_prompt[:200]}
success_criteria:
  - Goal decomposed into actionable subtasks
  - Each subtask has measurable completion criteria
subtasks:
  - id: st-1
    description: Analyze goal and identify best approach
    assignee: master
  - id: st-2
    description: Execute approach and verify result
    assignee: operator
notes: Demo mode — canned response. For real planning, configure LLM_API_KEY.
```"""

    def _master_response(self, user_prompt: str) -> str:
        """Мастер: technical plan with concrete steps."""
        return """```yaml
plan_id: plan-demo-001
subtask_id: st-1
strategy: Demo plan — 3 atomic steps with measurable verification
steps:
  - id: step-1
    action: Verify daemon is running and reachable
    tool: curl https://api.github.com/repos/makar52nn2016-jpg/crypto-daemon/actions/runs?per_page=1
    expected_output: JSON with workflow_runs[0].status=completed
    verification: HTTP 200 + JSON contains workflow_runs key
  - id: step-2
    action: Check current Frantic #136 claim status
    tool: curl -H "Authorization: Bearer $FRANTIC_AGENT_TOKEN" https://gofrantic.com/v1/claims/62e34461-7515-41ae-90ce-fc3e22ea2a83
    expected_output: JSON with status=delivered or status=accepted
    verification: HTTP 200 + JSON has status field
  - id: step-3
    action: Check if stompstart.com/api/startups/agentbounties is live
    tool: curl -o /dev/null -w '%{http_code}' https://stompstart.com/api/startups/agentbounties
    expected_output: HTTP 200 (if PR merged) or HTTP 404 (if still pending)
    verification: Either response code received
failure_modes:
  - scenario: GitHub API rate limited
    recovery: Wait 60s, retry with authenticated request
  - scenario: Frantic API token expired
    recovery: Re-authenticate at gofrantic.com/a/agent-b94b60
acceptance:
  - All 3 steps return measurable output
  - Artifacts saved to tasks/<task_id>/step-N.json
estimated_steps: 3
```"""

    def _operator_response(self, user_prompt: str) -> str:
        """Оператор: execute steps + save artifacts (simulated)."""
        return """```yaml
executed_steps:
  - step_id: step-1
    status: SUCCESS
    command: curl -s https://api.github.com/repos/makar52nn2016-jpg/crypto-daemon/actions/runs?per_page=1
    output: '{"workflow_runs":[{"status":"completed","conclusion":"success",...}]}'
    artifact_path: tasks/demo/step-1.json
    duration_sec: 2
  - step_id: step-2
    status: SUCCESS
    command: curl -s -H "Authorization: Bearer $FRANTIC_AGENT_TOKEN" https://gofrantic.com/v1/claims/62e34461-7515-41ae-90ce-fc3e22ea2a83
    output: '{"status":"delivered","judged_at":null,"quality":null}'
    artifact_path: tasks/demo/step-2.json
    duration_sec: 1
  - step_id: step-3
    status: SUCCESS
    command: curl -s -o /dev/null -w '%{http_code}' https://stompstart.com/api/startups/agentbounties
    output: '404'
    artifact_path: tasks/demo/step-3.json
    duration_sec: 1
errors: []
summary: All 3 verification steps completed successfully — daemon alive, Frantic claim delivered (pending review), stompstart.com not yet published
next_action: controller review — verify all step outputs are valid and match expected format
```"""

    def _controller_response(self, user_prompt: str) -> str:
        """Контролёр: independent verification."""
        return """```yaml
verdict: PASS
checks:
  - step_id: step-1
    expected: GitHub API returns workflow_runs array with completed status
    actual: Verified — latest run has status=completed, conclusion=success
    status: PASS
    evidence: "Direct curl to api.github.com confirmed response shape matches expected"
  - step_id: step-2
    expected: Frantic claim returns status field
    actual: Verified — status=delivered, judged_at=null (pending review)
    status: PASS
    evidence: "Direct curl to gofrantic.com confirmed claim UUID 62e34461 status=delivered"
  - step_id: step-3
    expected: stompstart.com responds with HTTP code
    actual: Verified — HTTP 404 (publication gate not yet met, expected since PR not merged)
    status: PASS
    evidence: "Direct curl to stompstart.com/api/startups/agentbounties returned 404"
issues:
  - severity: MINOR
    description: Stompstart publication gate not yet met (PR #9 still pending merge by @auscaster)
    fix: Wait for @auscaster to merge PR — Frantic auto-review will then pass
final_summary: All 3 demo steps verified independently. Daemon alive, Frantic claim in review queue, Stompstart publication pending PR merge.
```"""
