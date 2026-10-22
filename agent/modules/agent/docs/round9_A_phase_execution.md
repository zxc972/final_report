# Round 9 A: phase execution and request accounting

Only product_graph_planner uses the new execution card and phase exposure.
Legacy's 7652-byte system prompt, knowledge packages, original validator and
finalizer are unchanged. The requested gateway option omission and native HTTP
usage accounting are provider/request fixes, including explicitly routed runs.

Sealed: write_code, run_python, read_operations, finalize_artifacts. The model
request forces write_code until the sealed version has actually been written.
The execution guard denies all other tools, including stale parallel tool calls.
After an execution failure, read_file is additionally limited to /work error/log
or tool_results paths, with the existing 4000-character return ceiling; reflection
requires observation_id only. Direct host-side resealing remains versioned, but
is not exposed as a sealed-stage model tool. No scientific code is supplied.

Explicit upstream unsupported tool_choice has one bounded retry with only the
four-tool registry. Both HTTP attempts count. Other provider errors propagate.

commit_plan's model return contains the execution card (<=1500 characters) and
short state. All complete input paths, actual function signatures/return fields,
sealed script, outputs/columns and disclosure instructions are included. Complete
versioned execution bundles and label sets remain in /work and protected state.
Oversized cards are rejected before sealing so replanning remains possible.

Thinking is omitted for the confirmed inferaiapi gateway before the first HTTP.
CompatibleChatOpenAI records each coding/review HTTP attempt's reported usage in
the active ChatSession; failures retain unknown usage, and logical budget fallback
does not count metered calls twice. No token price is invented.

Tests: default 589 passed,15 skipped,54 subtests; container22 passed,9 subtests;
synthetic format/operations39 passed,1 skip(host SciPy unavailable); frontend42
passed,tsc/build passed. One updated scripted fixture initially omitted import re;
that fixture-only issue was repaired and the complete container set rerun. Original
failure logs retained. Actual production HTTP tests belong to a separate new batch.
