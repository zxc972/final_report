from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys,time
W=Path('/work');FS=Path('/opt/freesurfer-7.2.0');assert os.statvfs(os.environ['FS_LICENSE']).f_flag & os.ST_RDONLY;SUBJECTS=W/'region_subjects_v2';SUBJECTS.mkdir(exist_ok=False)
rows=json.loads((W/'ixi20_label_inputs.json').read_text());assert len(rows)==20
bases={'DK':'DKaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs','Destrieux':'CDaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs','DKT':'DKTaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
assets={};jobs=[]
for index,row in enumerate([{'subject':'fsaverage'}]+rows):
    sid=row['subject'];source=FS/'subjects/fsaverage' if sid=='fsaverage' else Path('/inputs')/str(index-1)
    root=SUBJECTS/sid;root.mkdir();(root/'surf').symlink_to(source/'surf',target_is_directory=True)
    if (source/'mri').exists():(root/'mri').symlink_to(source/'mri',target_is_directory=True)
    (root/'label').mkdir();(root/'scripts').mkdir()
    for hemi in ['lh','rh']:
        cortex=source/'label'/f'{hemi}.cortex.label';assert cortex.exists(),cortex
        (root/'label'/cortex.name).symlink_to(cortex)
        if sid=='fsaverage':
            for stem in ['aparc','aparc.a2009s']:(root/'label'/f'{hemi}.{stem}.annot').symlink_to(source/'label'/f'{hemi}.{stem}.annot')
            wanted=['DKT']
        else:
            mapped=source/'label'/f'{hemi}.aparc.DKTatlas.mapped.annot';assert mapped.exists(),mapped
            (root/'label'/f'{hemi}.aparc.DKTatlas.annot').symlink_to(mapped);wanted=['DK','Destrieux']
        for rel in [f'surf/{hemi}.sphere.reg',f'surf/{hemi}.white',f'surf/{hemi}.curv',f'surf/{hemi}.sulc',f'surf/{hemi}.smoothwm',f'label/{hemi}.cortex.label']+([] if sid=='fsaverage' else [f'label/{hemi}.aparc.DKTatlas.mapped.annot']):
            p=source/rel;assert p.exists(),p;assets[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}
        aseg=source/'mri/aseg.presurf.mgz'
        if aseg.exists():assets[str(aseg)]={'sha256':sha(aseg),'bytes':aseg.stat().st_size,'mtime_ns':aseg.stat().st_mtime_ns}
        for atlas in wanted:
            classifier=FS/'average'/f'{hemi}.{bases[atlas]}';assert classifier.exists()
            stem={'DK':'aparc','Destrieux':'aparc.a2009s','DKT':'aparc.DKTatlas'}[atlas];output=root/'label'/f'{hemi}.{stem}.annot'
            command=[str(FS/'bin/mris_ca_label'),'-seed','1234','-l',str(cortex)]
            if aseg.exists():command+=['-aseg',str(aseg)]
            command += [sid,hemi,str(source/'surf'/f'{hemi}.sphere.reg'),str(classifier),str(output)]
            jobs.append({'subject':sid,'hemisphere':hemi,'atlas':atlas,'command':command,'classifier':classifier.name,'classifier_sha256':sha(classifier),'output':str(output),'aseg_presurf_used':aseg.exists()})
save(W/'region_input_fingerprints_before.json',assets);save(W/'region_label_jobs.json',jobs)
def one(job):
    name=job['subject']+'_'+job['hemisphere']+'_'+job['atlas'];logs=W/'region_label_logs_v2'/name;logs.mkdir(parents=True);started=time.monotonic();env=dict(os.environ);env.update(SUBJECTS_DIR=str(SUBJECTS),FREESURFER_HOME=str(FS),TMPDIR=str(logs),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    with (logs/'stdout.txt').open('w') as so,(logs/'stderr.txt').open('w') as se:
        r=subprocess.run(job['command'],env=env,cwd=logs,stdin=subprocess.DEVNULL,stdout=so,stderr=se,timeout=900)
    output=Path(job['output']);rec={**job,'exit_code':r.returncode,'elapsed_seconds':time.monotonic()-started,'output_exists':output.exists(),'output_sha256':sha(output) if output.exists() else None};save(logs/'receipt.json',rec);print(json.dumps({k:rec[k] for k in ['subject','hemisphere','atlas','exit_code','elapsed_seconds','output_exists']}),flush=True)
    assert r.returncode==0 and output.exists(),name
    return rec
# First verify one template and one native subject before the remaining jobs.
pilots=[next(x for x in jobs if x['subject']=='fsaverage' and x['hemisphere']=='lh'),next(x for x in jobs if x['subject']=='IXI026' and x['hemisphere']=='lh' and x['atlas']=='DK')]
receipts=[one(j) for j in pilots]
remaining=[j for j in jobs if j not in pilots]
with ThreadPoolExecutor(max_workers=2) as pool:
    for future in as_completed([pool.submit(one,j) for j in remaining]):receipts.append(future.result())
assert len(receipts)==82
changed=[p for p,v in assets.items() if sha(Path(p))!=v['sha256'] or Path(p).stat().st_mtime_ns!=v['mtime_ns']];assert not changed,changed
save(W/'region_label_generation.json',{'completed':True,'jobs':receipts,'original_input_changes':changed,'model_calls':0,'original_inputs_read_only':True,'template_aseg_note':'Use recon-all default -aseg only where the exact aseg.presurf.mgz exists; fsaverage lacks that volume if recorded false','classifier_selection':'Exact default recon-all 7.2 GCS variables, not optional -dkt2020 or historical alternatives'})
command=[sys.executable,'-I','-B','/src/tools/knowledge/run_region_resolution.py','--subjects-dir',str(SUBJECTS)]
for sid in ['fsaverage']+[r['subject'] for r in rows]:command+=['--subject',sid]
command+=['--out','/work/region_resolution_v2']
with (W/'region_resolution_v2.stdout.log').open('w') as so,(W/'region_resolution_v2.stderr.log').open('w') as se:r=subprocess.run(command,cwd=W,stdin=subprocess.DEVNULL,stdout=so,stderr=se,timeout=1800)
save(W/'region_resolution_v2.status.json',{'exit_code':r.returncode,'subjects':21,'classifier_jobs':82,'model_calls':0,'original_inputs_changed':False,'completed_utc':datetime.now(timezone.utc).isoformat()});assert r.returncode==0
