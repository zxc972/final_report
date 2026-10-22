# R9 A post-trial offline follow-up

Paid source and all four paid outcomes remain unchanged at46ba0b0. No additional
real model call is authorized by this offline follow-up. Both model-stop markers
remain in force, independently of the unused monetary/call ceiling.

The supplied internal-review context already included actual protected execution
receipts but omitted their IDs from registered_evidence_ids. The model cited those
real IDs and strict parse_review consequently rejected the response. Add only IDs
from actual_execution_receipts in product_graph_planner only; legacy keeps its
previous registry behavior. Unknown pointers remain rejected. parse_review,
ArtifactValidator and the original finalizer module are unchanged.

Replaying the two original review HTTP responses offline changes their protocol
interpretation from invalid to pass(P1_1) and revise(P1_2), respectively. This is
not a new model response or a retroactive paid success. P1_1 CSV precision still
fails the frozen numerical tolerance. P1_2 revise still requires an actual Agent
repair run; it is never relabeled accepted.

A valid revise after automatic finalization must reopen the model's repair tool
set. The repair node writes the actual validator feedback to /work/tool_results,
records executed_failed, and requires a new successful execution before another
finalization. Old protected receipts remain. The old completed-code/manifest
receipts cannot bypass the pending review. After a repair, a C conclusion bound
to the old execution receipt is stale and must be submitted again.

Offline tests cover valid receipt IDs plus rejection of unknown IDs,
manual-finalize bypass prevention, and an actual Deep Agents ToolNode loop with
a controlled revise then pass reviewer. The loop has both a fake-executor unit
case and an opt-in real Apptainer case using only synthetic CSV/JSON files;
no subject images or provider calls are involved. No test
assertion is relaxed. Final default626 passed/16 skipped/54 subtests; the existing22 sandbox
cases plus the new synthetic review-repair container case passed; unchanged frontend50 passed plus tsc/build. Real retesting of
this follow-up belongs to a separately reviewed new cohort, not the stopped R9 one.
