# Round23 condition test v2 and combined evaluation

Algorithm, prompts, vocabulary, slots, score definitions and settings match Round18. V1 predictions are reused byte-for-byte; only the 83 new statements receive model calls.
Bootstrap: 2000 paired statement resamples, seed 20261023; combined sets preserve each test set size in every resample. Pending labels are scored as supplied.

Primary sensitivity excludes the seven pending v2 items; an additional combined sensitivity excludes all thirteen pending v1+v2 items. No defaults are adjusted.

## v2_83

| 组别 | 模板准确率 % | 可执行 P/R/F1 % | 非可执行 P/R/F1 % | 规范键 P/R/F1 % | 审核条数 |
|---|---:|---|---|---|---:|
| full_v2 | 78.31 | 53.85/46.67/50.00 | 88.57/91.18/89.86 | 27.27/23.08/25.00 | 14 |
| k1_v2 | 79.52 | 45.00/60.00/51.43 | 90.48/83.82/87.02 | 23.53/30.77/26.67 | 6 |
| direct_v2 | 79.52 | 50.00/80.00/61.54 | 94.92/82.35/88.19 | 0.00/0.00/0.00 | 0 |
| retrieval_only | 10.84 | 18.52/100.00/31.25 | 100.00/2.94/5.71 | 0.00/0.00/0.00 | 0 |

| 指标：点估计 [95% CI]，除审核数外均为 % | full_v2 | k1_v2 | direct_v2 | retrieval_only |
|---|---:|---:|---:|---:|
| template_accuracy | 78.31 [68.67, 86.75] | 79.52 [71.05, 87.95] | 79.52 [69.88, 87.95] | 10.84 [4.82, 18.07] |
| executable.precision | 53.85 [25.00, 81.82] | 45.00 [22.73, 67.86] | 50.00 [27.78, 70.38] | 18.52 [10.00, 27.50] |
| executable.recall | 46.67 [20.00, 71.45] | 60.00 [33.33, 83.33] | 80.00 [57.14, 100.00] | 100.00 [100.00, 100.00] |
| executable.f1 | 50.00 [23.99, 70.59] | 51.43 [28.57, 70.00] | 61.54 [38.88, 77.78] | 31.25 [18.18, 43.14] |
| advisory_or_not_executable.precision | 88.57 [80.00, 95.59] | 90.48 [82.26, 96.83] | 94.92 [88.71, 100.00] | 100.00 [0.00, 100.00] |
| advisory_or_not_executable.recall | 91.18 [83.78, 97.14] | 83.82 [74.54, 92.19] | 82.35 [73.02, 91.18] | 2.94 [0.00, 7.58] |
| advisory_or_not_executable.f1 | 89.86 [83.82, 94.74] | 87.02 [80.00, 92.75] | 88.19 [81.67, 93.94] | 5.71 [0.00, 14.08] |
| key.precision | 27.27 [12.50, 50.00] | 23.53 [9.09, 40.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.recall | 23.08 [10.00, 40.00] | 30.77 [12.50, 50.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.f1 | 25.00 [11.11, 40.00] | 26.67 [11.11, 42.11] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| review_queue | 14.00 [8.00, 21.00] | 6.00 [2.00, 11.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |

## v2_nonpending_76

| 组别 | 模板准确率 % | 可执行 P/R/F1 % | 非可执行 P/R/F1 % | 规范键 P/R/F1 % | 审核条数 |
|---|---:|---|---|---|---:|
| full_v2 | 85.53 | 63.64/53.85/58.33 | 90.77/93.65/92.19 | 30.00/27.27/28.57 | 10 |
| k1_v2 | 84.21 | 53.33/61.54/57.14 | 91.80/88.89/90.32 | 28.57/36.36/32.00 | 5 |
| direct_v2 | 84.21 | 57.89/84.62/68.75 | 96.49/87.30/91.67 | 0.00/0.00/0.00 | 0 |
| retrieval_only | 11.84 | 17.57/100.00/29.89 | 100.00/3.17/6.15 | 0.00/0.00/0.00 | 0 |

| 指标：点估计 [95% CI]，除审核数外均为 % | full_v2 | k1_v2 | direct_v2 | retrieval_only |
|---|---:|---:|---:|---:|
| template_accuracy | 85.53 [77.63, 92.14] | 84.21 [76.32, 92.11] | 84.21 [75.00, 92.11] | 11.84 [5.23, 19.74] |
| executable.precision | 63.64 [33.27, 90.00] | 53.33 [28.55, 78.57] | 57.89 [34.78, 80.00] | 17.57 [9.46, 26.67] |
| executable.recall | 53.85 [23.53, 81.82] | 61.54 [33.33, 88.89] | 84.62 [62.50, 100.00] | 100.00 [100.00, 100.00] |
| executable.f1 | 58.33 [28.57, 80.00] | 57.14 [31.58, 76.19] | 68.75 [46.65, 85.71] | 29.89 [17.28, 42.11] |
| advisory_or_not_executable.precision | 90.77 [83.08, 97.01] | 91.80 [84.13, 98.31] | 96.49 [90.91, 100.00] | 100.00 [0.00, 100.00] |
| advisory_or_not_executable.recall | 93.65 [87.30, 98.48] | 88.89 [80.65, 95.52] | 87.30 [78.33, 95.16] | 3.17 [0.00, 8.20] |
| advisory_or_not_executable.f1 | 92.19 [87.02, 96.35] | 90.32 [84.55, 95.38] | 91.67 [85.96, 96.19] | 6.15 [0.00, 15.15] |
| key.precision | 30.00 [12.50, 60.00] | 28.57 [12.50, 50.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.recall | 27.27 [11.11, 50.00] | 36.36 [14.29, 60.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.f1 | 28.57 [12.50, 46.15] | 32.00 [13.33, 50.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| review_queue | 10.00 [5.00, 16.00] | 5.00 [1.00, 9.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |

## combined_128

| 组别 | 模板准确率 % | 可执行 P/R/F1 % | 非可执行 P/R/F1 % | 规范键 P/R/F1 % | 审核条数 |
|---|---:|---|---|---|---:|
| full_v2 | 81.25 | 60.00/50.00/54.55 | 88.89/92.31/90.57 | 44.44/36.36/40.00 | 15 |
| k1_v2 | 81.25 | 51.72/62.50/56.60 | 90.91/86.54/88.67 | 38.46/45.45/41.67 | 7 |
| direct_v2 | 80.47 | 52.94/75.00/62.07 | 93.62/84.62/88.89 | 0.00/0.00/0.00 | 0 |
| retrieval_only | 11.72 | 19.35/100.00/32.43 | 100.00/3.85/7.41 | 0.00/0.00/0.00 | 0 |

| 指标：点估计 [95% CI]，除审核数外均为 % | full_v2 | k1_v2 | direct_v2 | retrieval_only |
|---|---:|---:|---:|---:|
| template_accuracy | 81.25 [74.22, 87.50] | 81.25 [74.22, 87.50] | 80.47 [73.44, 86.72] | 11.72 [6.25, 17.19] |
| executable.precision | 60.00 [37.50, 79.33] | 51.72 [33.33, 69.57] | 52.94 [35.14, 70.00] | 19.35 [12.60, 26.40] |
| executable.recall | 50.00 [29.62, 70.00] | 62.50 [42.86, 81.82] | 75.00 [57.13, 91.67] | 100.00 [100.00, 100.00] |
| executable.f1 | 54.55 [34.28, 70.59] | 56.60 [38.29, 71.88] | 62.07 [45.45, 75.76] | 32.43 [22.38, 41.77] |
| advisory_or_not_executable.precision | 88.89 [82.52, 94.55] | 90.91 [84.78, 96.08] | 93.62 [88.42, 97.87] | 100.00 [100.00, 100.00] |
| advisory_or_not_executable.recall | 92.31 [86.54, 97.00] | 86.54 [79.81, 93.00] | 84.62 [77.55, 91.09] | 3.85 [0.91, 8.41] |
| advisory_or_not_executable.f1 | 90.57 [86.14, 94.39] | 88.67 [83.67, 93.00] | 88.89 [83.87, 93.07] | 7.41 [1.80, 15.52] |
| key.precision | 44.44 [27.27, 63.64] | 38.46 [23.52, 50.07] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.recall | 36.36 [21.43, 50.08] | 45.45 [28.57, 60.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.f1 | 40.00 [25.00, 53.85] | 41.67 [25.81, 53.85] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| review_queue | 15.00 [8.98, 22.00] | 7.00 [2.00, 12.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |

## combined_exclude_v2_pending_121

| 组别 | 模板准确率 % | 可执行 P/R/F1 % | 非可执行 P/R/F1 % | 规范键 P/R/F1 % | 审核条数 |
|---|---:|---|---|---|---:|
| full_v2 | 85.95 | 66.67/54.55/60.00 | 90.29/93.94/92.08 | 47.06/40.00/43.24 | 11 |
| k1_v2 | 84.30 | 58.33/63.64/60.87 | 91.75/89.90/90.82 | 43.48/50.00/46.51 | 6 |
| direct_v2 | 83.47 | 58.62/77.27/66.67 | 94.57/87.88/91.10 | 0.00/0.00/0.00 | 0 |
| retrieval_only | 12.40 | 18.80/100.00/31.65 | 100.00/4.04/7.77 | 0.00/0.00/0.00 | 0 |

| 指标：点估计 [95% CI]，除审核数外均为 % | full_v2 | k1_v2 | direct_v2 | retrieval_only |
|---|---:|---:|---:|---:|
| template_accuracy | 85.95 [80.14, 91.74] | 84.30 [77.69, 90.08] | 83.47 [76.86, 90.08] | 12.40 [6.61, 18.18] |
| executable.precision | 66.67 [44.44, 88.24] | 58.33 [37.50, 77.28] | 58.62 [40.91, 76.92] | 18.80 [11.97, 26.05] |
| executable.recall | 54.55 [33.33, 75.00] | 63.64 [42.11, 83.33] | 77.27 [58.33, 94.12] | 100.00 [100.00, 100.00] |
| executable.f1 | 60.00 [40.00, 76.19] | 60.87 [41.17, 76.19] | 66.67 [50.00, 80.70] | 31.65 [21.37, 41.33] |
| advisory_or_not_executable.precision | 90.29 [84.26, 95.37] | 91.75 [86.02, 96.91] | 94.57 [89.89, 98.86] | 100.00 [100.00, 100.00] |
| advisory_or_not_executable.recall | 93.94 [89.22, 98.04] | 89.90 [84.04, 95.65] | 87.88 [81.44, 94.00] | 4.04 [0.97, 8.25] |
| advisory_or_not_executable.f1 | 92.08 [87.96, 95.69] | 90.82 [86.32, 94.74] | 91.10 [86.67, 95.00] | 7.77 [1.92, 15.24] |
| key.precision | 47.06 [30.00, 66.67] | 43.48 [26.63, 60.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.recall | 40.00 [23.08, 57.14] | 50.00 [30.00, 64.35] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.f1 | 43.24 [26.09, 58.83] | 46.51 [28.57, 60.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| review_queue | 11.00 [6.00, 17.00] | 6.00 [2.00, 11.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |

## combined_exclude_all_pending_115

| 组别 | 模板准确率 % | 可执行 P/R/F1 % | 非可执行 P/R/F1 % | 规范键 P/R/F1 % | 审核条数 |
|---|---:|---|---|---|---:|
| full_v2 | 87.83 | 68.75/57.89/62.86 | 91.92/94.79/93.33 | 46.67/41.18/43.75 | 11 |
| k1_v2 | 86.09 | 57.14/63.16/60.00 | 92.55/90.62/91.58 | 45.00/52.94/48.65 | 6 |
| direct_v2 | 86.09 | 60.00/78.95/68.18 | 95.56/89.58/92.47 | 0.00/0.00/0.00 | 0 |
| retrieval_only | 12.17 | 17.12/100.00/29.23 | 100.00/4.17/8.00 | 0.00/0.00/0.00 | 0 |

| 指标：点估计 [95% CI]，除审核数外均为 % | full_v2 | k1_v2 | direct_v2 | retrieval_only |
|---|---:|---:|---:|---:|
| template_accuracy | 87.83 [81.74, 93.04] | 86.09 [80.00, 92.17] | 86.09 [80.00, 92.17] | 12.17 [6.09, 18.26] |
| executable.precision | 68.75 [43.73, 91.31] | 57.14 [34.78, 78.26] | 60.00 [40.00, 79.17] | 17.12 [10.62, 24.77] |
| executable.recall | 57.89 [33.33, 79.17] | 63.16 [38.45, 83.33] | 78.95 [59.98, 95.00] | 100.00 [100.00, 100.00] |
| executable.f1 | 62.86 [40.00, 79.09] | 60.00 [37.84, 76.00] | 68.18 [50.00, 82.36] | 29.23 [19.20, 39.71] |
| advisory_or_not_executable.precision | 91.92 [86.27, 96.91] | 92.55 [86.66, 96.88] | 95.56 [91.11, 98.94] | 100.00 [100.00, 100.00] |
| advisory_or_not_executable.recall | 94.79 [89.90, 98.94] | 90.62 [84.62, 95.88] | 89.58 [83.33, 95.00] | 4.17 [1.01, 8.33] |
| advisory_or_not_executable.f1 | 93.33 [89.36, 96.55] | 91.58 [87.15, 95.19] | 92.47 [88.17, 95.96] | 8.00 [2.00, 15.38] |
| key.precision | 46.67 [28.57, 66.67] | 45.00 [27.27, 61.54] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.recall | 41.18 [22.22, 58.33] | 52.94 [33.33, 69.23] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| key.f1 | 43.75 [25.00, 60.00] | 48.65 [30.00, 63.16] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| review_queue | 11.00 [5.00, 18.00] | 6.00 [2.00, 11.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |

## McNemar exact paired tests

```json
{
  "v2_83": {
    "full_v2_vs_direct_v2": {
      "n": 83,
      "both_correct": 55,
      "first_only_correct": 11,
      "second_only_correct": 1,
      "neither_correct": 16,
      "discordant": 12,
      "p_exact_two_sided": 0.00634765625,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 66,
      "second_correct": 56
    },
    "k1_v2_vs_direct_v2": {
      "n": 83,
      "both_correct": 52,
      "first_only_correct": 10,
      "second_only_correct": 4,
      "neither_correct": 17,
      "discordant": 14,
      "p_exact_two_sided": 0.1795654296875,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 62,
      "second_correct": 56
    }
  },
  "v2_nonpending_76": {
    "full_v2_vs_direct_v2": {
      "n": 76,
      "both_correct": 55,
      "first_only_correct": 8,
      "second_only_correct": 0,
      "neither_correct": 13,
      "discordant": 8,
      "p_exact_two_sided": 0.0078125,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 63,
      "second_correct": 55
    },
    "k1_v2_vs_direct_v2": {
      "n": 76,
      "both_correct": 52,
      "first_only_correct": 9,
      "second_only_correct": 3,
      "neither_correct": 12,
      "discordant": 12,
      "p_exact_two_sided": 0.14599609375,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 61,
      "second_correct": 55
    }
  },
  "combined_128": {
    "full_v2_vs_direct_v2": {
      "n": 128,
      "both_correct": 87,
      "first_only_correct": 18,
      "second_only_correct": 1,
      "neither_correct": 22,
      "discordant": 19,
      "p_exact_two_sided": 7.62939453125e-05,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 105,
      "second_correct": 88
    },
    "k1_v2_vs_direct_v2": {
      "n": 128,
      "both_correct": 84,
      "first_only_correct": 16,
      "second_only_correct": 4,
      "neither_correct": 24,
      "discordant": 20,
      "p_exact_two_sided": 0.01181793212890625,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 100,
      "second_correct": 88
    }
  },
  "combined_exclude_v2_pending_121": {
    "full_v2_vs_direct_v2": {
      "n": 121,
      "both_correct": 87,
      "first_only_correct": 15,
      "second_only_correct": 0,
      "neither_correct": 19,
      "discordant": 15,
      "p_exact_two_sided": 6.103515625e-05,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 102,
      "second_correct": 87
    },
    "k1_v2_vs_direct_v2": {
      "n": 121,
      "both_correct": 84,
      "first_only_correct": 15,
      "second_only_correct": 3,
      "neither_correct": 19,
      "discordant": 18,
      "p_exact_two_sided": 0.007537841796875,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 99,
      "second_correct": 87
    }
  },
  "combined_exclude_all_pending_115": {
    "full_v2_vs_direct_v2": {
      "n": 115,
      "both_correct": 86,
      "first_only_correct": 13,
      "second_only_correct": 0,
      "neither_correct": 16,
      "discordant": 13,
      "p_exact_two_sided": 0.000244140625,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 99,
      "second_correct": 86
    },
    "k1_v2_vs_direct_v2": {
      "n": 115,
      "both_correct": 83,
      "first_only_correct": 13,
      "second_only_correct": 3,
      "neither_correct": 16,
      "discordant": 16,
      "p_exact_two_sided": 0.021270751953125,
      "method": "exact binomial McNemar, unadjusted",
      "first_correct": 96,
      "second_correct": 86
    }
  }
}
```

Full-v2 error statements, supplied gold, predictions and reasons: errors_full_v2.json / .csv.
