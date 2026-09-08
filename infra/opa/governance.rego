# ReturnGuard — the GovernanceGate decision, as policy.
#
# The pipeline sends the case attributes as `input`; this returns
#   { "route": "auto_approve" | "escalate", "reasons": [ ... ] }
# The route is the ONLY thing that finalizes a return. auto_approve requires
# EVERY condition below to hold; anything else is a human review.
#
# The QA-sampling dice roll and all DB / audit writes stay in the worker
# (worker/pipeline/governance.py) — this file owns the decision, not the effects.

package returnguard.governance

default route := "escalate"

route := "auto_approve" if {
	not input.kill_switch
	input.dq_ok
	input.proposed == "approve"
	not input.high_value
	not input.critic_veto
	input.risk < input.tau_risk
	input.confidence > input.tau_conf
	input.automation_level in {"assist", "auto"}
}

# --- human-readable reasons (order of the checks in the original gate) ----------

reasons contains "kill switch is on — every case goes to human review" if input.kill_switch

reasons contains sprintf("data-quality gate failed: %s", [_dq_reason]) if {
	not input.kill_switch
	not input.dq_ok
}

_dq_reason := r if {
	r := input.dq_reason
	r != ""
} else := "insufficient data"

reasons contains "auto-deny is never final; routed for human confirmation of the denial" if {
	not input.kill_switch
	input.dq_ok
	input.proposed == "deny"
}

reasons contains "refund exceeds the high-value threshold; human sign-off required" if {
	not input.kill_switch
	input.dq_ok
	input.proposed != "deny"
	input.high_value
}

reasons contains sprintf("Critic vetoed: %s", [object.get(input, "critic_concern", "")]) if {
	not input.kill_switch
	input.dq_ok
	input.proposed != "deny"
	not input.high_value
	input.critic_veto
}

reasons contains sprintf(
	"auto-approved: risk %.2f < %v, confidence %.2f > %v, level=%s, no Critic veto",
	[input.risk, input.tau_risk, input.confidence, input.tau_conf, input.automation_level],
) if route == "auto_approve"

reasons contains sprintf(
	"not eligible for auto-approve (risk %.2f / conf %.2f vs tau %v/%v)",
	[input.risk, input.confidence, input.tau_risk, input.tau_conf],
) if {
	route == "escalate"
	not input.kill_switch
	input.dq_ok
	input.proposed == "approve"
	not input.high_value
	not input.critic_veto
	input.automation_level in {"assist", "auto"}
}

reasons contains sprintf("automation_level=%s: agent decides, human acts", [input.automation_level]) if {
	route == "escalate"
	not input.kill_switch
	input.dq_ok
	input.proposed != "deny"
	not input.high_value
	not input.critic_veto
	input.automation_level in {"shadow", "suggest"}
}

decision := {"route": route, "reasons": [r | some r in reasons]}
