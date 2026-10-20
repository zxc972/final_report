from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil

root=Path('/data/xuancheng/structural_env')
names=['existing-references.json','PythonAnalysis.json','python-smoke.json','HumanTemplates.json','human-template-smoke.json','structural_templates_20261013.json','AFNI_C3D.json','SynthStrip.json','integration-smoke.json']
index=[]
for name in names:
    path=root/'manifests'/name
    if not path.is_file(): raise SystemExit('Missing final component manifest: '+str(path))
    content=path.read_bytes()
    json.loads(content)
    index.append({'path':str(path),'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
for image in ['primatex-legacy.sif','fastsurfer-cu118.sif','afni-c3d.sif','synthstrip-cpu.sif']:
    if not (root/'images'/image).is_file(): raise SystemExit('Missing container: '+image)
integration=json.loads((root/'manifests/integration-smoke.json').read_text())
if integration['status'] != 'pass': raise SystemExit('Integration test failed')
manifest={
    'schema_version':1,
    'created_utc':datetime.now(timezone.utc).isoformat(),
    'status':'deployed_and_smoke_verified',
    'server':'xuancheng@192.168.2.110',
    'root':str(root),
    'container_runtime':'Apptainer 1.4.5-2.el9',
    'activate':str(root/'activate.sh'),
    'launcher':str(root/'bin/structural-env'),
    'new_components':['AFNI 26.3.02','Convert3D 1.4.4','SynthStrip fixed official source cf4bccf CPU build','Nilearn 0.14.1','Nipype 1.11.0','PyBIDS 0.22.0','NMT v2.0 symmetric with CHARM/SARM','MBMv3 volumetric template distribution'],
    'reused':['PrimateX_1_7.sif','FastSurfer cu118 existing SIF','existing PrimateX model directories','existing FSL MNI standard templates','existing migrated fsaverage'],
    'components':index,
    'summary_validation':{
        'python_dependency_and_functional_checks':'pass',
        'nonhuman_template_nifti_full_reads':'128/128 pass',
        'nonhuman_template_geometry_pairs':'13/13 pass',
        'human_MNI_2mm_geometry_and_finite_data':'pass',
        'synthstrip_main_and_no_csf_inference':'both exit 0; shape/affine/binary nonempty mask verified',
        'launcher_and_AFNI_C3D_image_arithmetic':'pass',
        'real_subject_pipeline_accuracy':'not tested in this deployment'
    },
    'limitations':[
        'SynthStrip is a fixed official source CPU build; OCI tag 1.8 was unavailable and identity to that OCI image is not asserted.',
        'AFNI R-dependent statistics are not configured.',
        'Nipype analysis container and standalone AFNI/C3D/SynthStrip images require explicit cross-container orchestration.',
        'Existing images/models/fsaverage are absolute path references; preserve referenced resources when migrating.',
        'Tools were not automatically added to the PrimateX Agent registry.'
    ],
    'license_key_handling':'existing FreeSurfer key read-only runtime bind; not embedded in new images',
    'disk_free_bytes':shutil.disk_usage(root).free,
}
target=root/'manifests/environment-20261013.json'
temporary=target.with_suffix('.json.tmp')
temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
temporary.replace(target)
print(json.dumps(manifest,ensure_ascii=False,indent=2))
