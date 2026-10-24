# Round23 audited results

Runtime source: `1767b2179959352170a81d0dbf90e6ae9267f014`; evaluation source: `0a3fc77f99ec9d2a7c7e78ccfde97992ffd79e20`. No runtime changes during the six original-question trials.

- [Complete Chinese report](reports/round23_main_report_zh.md)
- [Condition test v2: metrics, intervals and errors](reports/condition_canon_test_v2_zh.md)
- [Region resolver supplement](reports/region_resolution_v2_zh.md)
- [Per-run records](report/run_summaries.json), [phases](report/stages.csv), [table checks](report/table_verification.csv), [meter alignment](report/meter_alignment.json)
- [Review protocol](report/internal_review_protocol_observations.json), [failure details](report/failure_details.json), [conclusion cards](report/conclusion_cards.json)
- [Safety audit](report/final_safety_audit.json), [delivery cross-check](delivery_audit.json)
- [Offline gates](offline/offline_all_passed.json), [unchanged-byte logs](offline/logs_manifest.json), [protected changes](offline/protected_review.json)

Actual analysis entries: 6; original-question full-chain passes: 1; both requested tables independently verified in 4 runs. Analysis: 119 logical calls / 131 HTTP attempts, 14 attempts without usage. Condition evaluation: 596 HTTP attempts, within its 1500 cap. No model calls in report/audit or region experiments.

The 24 report files were checked against the host export SHA manifest. Raw analysis provider bodies, per-subject numeric CSVs and executed source remain in the private archive on 6007. No MRI or raw provider bodies are included here. Existing services and the 244 frozen runtime files were unchanged; only the new loopback instance was stopped.
