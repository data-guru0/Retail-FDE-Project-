# ReturnGuard — per-agent least privilege, as policy.
#
#   input {agent, tool}  -> data.returnguard.authz.allow_tool   (bool)
#   input {agent, role}  -> data.returnguard.authz.allow_model  (bool)
#
# This is the enforced check on the hot path: ContextForge OSS filters
# tools/list but not tools/call, and Bifrost OSS virtual keys scope models but
# don't bind provider creds — so the worker asks OPA before every tool call and
# every model call. worker/pipeline/mcp_client.py and models_config.py keep an
# offline copy of these two maps and MUST stay in sync with this file.

package returnguard.authz

tool_grants := {
	"intake": ["get_order"],
	"policy": ["check_policy"],
	"behavior": ["get_customer_history", "flag_ring"],
	"decision": ["get_order", "check_policy", "get_customer_history"],
	"planner": [],
	"image": [],
	"critic": [],
	"explanation": [],
}

model_grants := {
	"planner": ["fast"],
	"intake": ["fast"],
	"policy": ["reason", "embed"],
	"image": ["vision"],
	"behavior": ["reason"],
	"decision": ["reason", "deep"],
	"critic": ["deep"],
	"explanation": ["deep"],
}

default allow_tool := false

allow_tool if input.tool in object.get(tool_grants, input.agent, [])

default allow_model := false

allow_model if input.role in object.get(model_grants, input.agent, [])
