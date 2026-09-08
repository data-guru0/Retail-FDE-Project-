# Runnable checks for the ReturnGuard policies.  `opa test infra/opa`
# (also run by `make opa-test` and inside scripts/verify_security.py).

package returnguard.governance_test

import data.returnguard.governance

_clean := {
	"kill_switch": false, "dq_ok": true, "dq_reason": "",
	"proposed": "approve", "high_value": false, "critic_veto": false,
	"risk": 0.05, "confidence": 0.90, "tau_risk": 0.30, "tau_conf": 0.80,
	"automation_level": "assist",
}

test_clean_case_auto_approves if {
	governance.decision.route == "auto_approve" with input as _clean
}

test_shadow_never_auto_approves if {
	governance.decision.route == "escalate" with input as object.union(_clean, {"automation_level": "shadow"})
}

test_kill_switch_forces_escalate if {
	governance.decision.route == "escalate" with input as object.union(_clean, {"kill_switch": true})
}

test_proposed_deny_is_never_final if {
	governance.decision.route == "escalate" with input as object.union(_clean, {"proposed": "deny"})
}

test_high_value_forces_human if {
	governance.decision.route == "escalate" with input as object.union(_clean, {"high_value": true})
}

test_critic_veto_forces_escalate if {
	governance.decision.route == "escalate" with input as object.union(_clean, {"critic_veto": true})
}

test_risk_over_threshold_escalates if {
	governance.decision.route == "escalate" with input as object.union(_clean, {"risk": 0.5})
}

test_low_confidence_escalates if {
	governance.decision.route == "escalate" with input as object.union(_clean, {"confidence": 0.5})
}

test_data_quality_failure_escalates if {
	d := governance.decision with input as object.union(_clean, {"dq_ok": false, "dq_reason": "no photo"})
	d.route == "escalate"
	d.reasons[_] == "data-quality gate failed: no photo"
}
