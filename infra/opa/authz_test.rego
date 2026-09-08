# Runnable checks for the ReturnGuard authz policy.  `opa test infra/opa`

package returnguard.authz_test


import data.returnguard.authz

test_behavior_may_flag_ring if {
	authz.allow_tool with input as {"agent": "behavior", "tool": "flag_ring"}
}

test_image_may_not_flag_ring if {
	not authz.allow_tool with input as {"agent": "image", "tool": "flag_ring"}
}

test_image_has_no_tools_at_all if {
	not authz.allow_tool with input as {"agent": "image", "tool": "get_order"}
}

test_image_may_use_vision_model if {
	authz.allow_model with input as {"agent": "image", "role": "vision"}
}

test_image_may_not_use_reason_model if {
	not authz.allow_model with input as {"agent": "image", "role": "reason"}
}

test_explanation_may_not_use_reason_model if {
	not authz.allow_model with input as {"agent": "explanation", "role": "reason"}
}
