"""Multi-subject struct fixtures; all arrays and metadata are synthetic."""
import copy,csv,importlib,json,struct
from pathlib import Path
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products,p
from test_round10_independent_numeric import write_inputs


def fixture(tmp_path,monkeypatch,comparison='correlation',missing=None,singleton=False,unmatched=False):
    tools=setup_products(tmp_path,monkeypatch)
    worker=importlib.import_module(agent.__package__+'.analysis_profile_worker')
    parts=importlib.import_module(agent.__package__+'.analysis_participants')
    rows=[];roots=[];registry=[]
    for i in range(8):
        root=tools.input_roots[0] if i==0 else tmp_path/f'synthetic_{i}'
        root.mkdir(exist_ok=True);roots.append(root)
        # Erase only setup_products' synthetic annotation alternatives by excluding them from the profile.
        for hemi in ('lh','rh'):
            write_inputs(root,hemi,new_table=True)
            metric=root/'surf'/f'{hemi}.thickness'
            values=[0.,1.2+.07*i+.018*(i%3)**2,1.9+.04*i-.01*(i%3),2.3+.03*i+.025*((i+1)%3)**2,3.2+.08*i+.017*(i%2)]
            metric.write_bytes(b'\xff\xff\xff'+struct.pack('>iii',5,0,1)+struct.pack('>5f',*values))
            annot=root/'label'/f'{hemi}.aparc.DKTatlas.mapped.annot';annot.write_bytes((root/'label'/f'{hemi}.aparc.annot').read_bytes())
            vertices=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(1.,1.,1.)]
            faces=[(0,1,2),(0,1,3),(0,2,3),(1,2,4),(1,3,4),(2,3,4)]
            surface=root/'surf'/f'{hemi}.white'
            surface.write_bytes(b'\xff\xff\xfe'+b'synthetic\n\n'+struct.pack('>ii',5,6)+b''.join(struct.pack('>fff',*v) for v in vertices)+b''.join(struct.pack('>iii',*f) for f in faces))
            registration=root/'surf'/f'{hemi}.sphere.reg';registration.write_bytes(surface.read_bytes())
            for target in (metric,annot,root/'label'/f'{hemi}.cortex.label',surface,registration):
                item=worker.profile_file(target);item['path']=worker.field(f'/inputs/{i}/'+target.relative_to(root).as_posix(),target,'synthetic mapping');rows.append(item)
        registry.append({'path':str(root),'subject_id':f's{i}','dataset':'synthetic','species_declared':'human','source':'synthetic only'})
    table=tmp_path/'participants.tsv'
    columns=['subject_id','group','age','sex','site']
    if missing:columns.remove(missing)
    with table.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,delimiter='\t',extrasaction='ignore');writer.writeheader()
        for i in range(8):writer.writerow({'subject_id':f'absent{i}' if unmatched else f's{i}','group':'case' if (i==7 if singleton else i>=4) else 'control','age':20+i*3+(i%2),'sex':'M' if i%2 else 'F','site':['A','B','C'][i%3]})
    cat=tmp_path/'catalog.json';cat.write_text(json.dumps({'roots':registry,'participants_tables':[{'dataset':'synthetic','path':str(table),'id_column':'subject_id','source':'generated fixture','license':'synthetic'}]}))
    monkeypatch.setenv('AGENT_DATA_CATALOG',str(cat))
    tools.input_roots=roots;parts.register_tables(tools)
    metadata=worker.profile_file(tools.resolve(tools.participants_tables[0]['mapped_path']))
    metadata['path']=worker.field(tools.participants_tables[0]['mapped_path'],table,'synthetic mapping');rows.append(metadata)
    saved=tools.control_store.save('data_profile',{'schema_version':'primatex.data_profile.v1','files':rows,'physical_scale_verified':worker.field(None,'fixture','unverified')})
    monkeypatch.setattr(p,'ensure_profile',lambda *args:(saved,True))
    intent={'subjects':[f's{i}' for i in range(8)],'species':'human','measures':['thickness'],'regions':'DKT','comparison':comparison,'method_id':'method:v14:group_regional_glm','design':{'effect':'group' if comparison=='group' else 'age','covariates':[] if comparison=='group' else ['sex']}}
    if comparison=='group':intent['design']['reference']='control'
    return tools,intent
