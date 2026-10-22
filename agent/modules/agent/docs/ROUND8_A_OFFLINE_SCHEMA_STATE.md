# Round 8 A offline follow-up

The frozen real trial had one ToolNode argument rejection outside the normal
function body: it returned no phase state and was not counted by that function's
budget reservation. Preserve that trial unchanged. The offline-only follow-up
validates the same registered Pydantic schema inside the event-wrapped handler,
counts failed schema attempts, and returns structured errors with current phase.
Plain ToolMessages and denied tools also retain phase under product_graph_planner.
Other profiles, including legacy_v13, keep their previous behavior.

A scripted BaseChatModel uses the actual Deep Agents ToolNode and malformed
record_analysis_reflection arguments. No external HTTP/model or image processing
is performed. It checks both product and legacy behavior and denied-tool refusal.
This is an engineering regression; no new real trial is claimed. The original
requestBudget token aggregation gap is separately retained as a remaining issue.
