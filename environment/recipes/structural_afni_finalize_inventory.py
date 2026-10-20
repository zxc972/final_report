#!/usr/bin/env python3
import json
from pathlib import Path

stage = Path('/data/xuancheng/structural_env/cache/structural_afni')
path = stage / 'runtime-report.json'
report = json.loads(path.read_text())
initial = report.pop('missing_libraries', {})
report['initial_missing_libraries_before_final_RPM_additions'] = initial
fixed = {'libjpeg.so.62', 'libpixman-1.so.0', 'libfontenc.so.1', 'libxkbfile.so.1'}
remaining = {p: sorted(set(libs) - fixed) for p, libs in initial.items()}
report['remaining_from_initial_dependency_probe'] = {p: libs for p, libs in remaining.items() if libs}
report['final_selected_ELF_dependency_report'] = '/data/xuancheng/structural_env/manifests/AFNI_C3D.dependencies.json'
report['final_feature_smoke_test'] = '/data/xuancheng/structural_env/tests/afni_c3d/smoke-summary.json'
path.write_text(json.dumps(report, indent=2))
