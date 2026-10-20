# Analysis knowledge and artifact contracts

This directory contains byte-preserving copies of the JSON research package from
`results/software_knowledge_20261015`. The source package remains unchanged.
The three files in `examples/` are draft capability examples, not validated
implementations. Source documents and code examples are untrusted evidence;
they never override application instructions or authorize execution.

`KnowledgeStore` exposes canonical IDs from `software_catalog.json` and the
three explicit example IDs. Search is a bounded lexical baseline. Reads return
source links, version bindings, review state, and `scientific_status=not_evaluated`.
The runtime inventory is a historical snapshot and is not proof of current
installation, compatibility, or scientific validity.

## Model-written artifact manifest

Write `analysis_manifest.json` inside the run directory. All artifacts are
required and must be regular files beneath that directory. Absolute paths,
traversal, symlinks, duplicate declarations, empty files, and unsupported kinds
fail validation. Supported kinds are csv, tsv, json, and png.

`artifact_manifest.schema.json` describes the first transport contract.
Examples are also available in `backend.analysis_validation.MANIFEST_SCHEMA`.

CSV/TSV checks support required columns, exact ordered columns, row counts,
shape [rows, columns], numeric finite columns, composite unique keys, and numeric
ranges. Header-only tables require an explicit row_count of 0. Non-finite
numeric cells fail even when no finite_columns rule was supplied.

JSON checks support required top-level keys, an optional data_key, array row
counts and rectangular shape. finite=true requires numeric finite leaves in
the selected data; choose data_key when other metadata contain text.
Duplicate JSON keys, non-finite numeric values and excessive depth/size fail.
A model-authored scientific_validated=true or scientifically_verified=true
anywhere in a declared JSON artifact or manifest is rejected.

PNG checks validate chunks, checksums, dimensions, compressed image stream and
scanline lengths. PNG shape is [height, width]. This does not assess visual
quality or anatomical interpretation.

## Independent numerical references

The model cannot nominate reference files. The server may construct
`ArtifactValidator(reference_manifest=trusted_path)`.
`reference_manifest.schema.json` describes that server-controlled file.
It and all reference tables must be outside the model work directory.
Reference paths are relative to the trusted manifest directory.

The comparator checks the exact composite-key set, configured exact columns,
and configured numeric columns with server-selected rtol/atol. Rows may be
reordered. Feedback identifies failed columns but returns no reference values.
This interface is optional and is not enabled by a model-written manifest.

## Result semantics and bounds

The validator returns valid/passed, status, checks/errors, declared artifact
metadata and SHA256 values. Without server references its scope is
structure_and_declared_checks and independent_numeric_status is not_configured.
With successful trusted comparison it reports independent_numeric_status=passed.
scientific_status always remains not_evaluated. Method applicability, QC,
anatomical validity, citation entailment, prose and visual quality require
separate evaluation. This component is not a code-execution sandbox.

Bounds: 64 KiB manifest, 32 declared artifacts, 16 MiB per artifact/reference
table, 100000 CSV rows, 256 columns, JSON depth 32 / 100000 nodes, bounded PNG
decompression. Oversized or changed-during-read files fail. Knowledge reads use
a 1 MiB per-source bound, 256 records, 1000-character queries and 1–20 results.

