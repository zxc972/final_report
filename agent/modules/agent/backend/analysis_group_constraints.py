"""Method-specific instances of the generic condition templates."""
from pathlib import Path
from .analysis_condition_templates import evaluate
from .analysis_template_bindings import environment_for, unwrap

MID='method:v14:group_regional_glm'

def check_group(tools, plan, files):
    scope=plan['analysis_scope'];env=environment_for(files,plan,{})
    env.update(group_inference=True,group_design=scope)
    env['slots']['subject_table']=[v for v in env['slots']['products'] if v['type']=='type:SubjectTable']
    instances=[{'id':MID+':design:'+c,'template':'design_variable','parameters':{'slot':'subject_table','variable':c},'severity':'hard'} for c in [scope['design']['effect'],*scope['design']['covariates']]]
    instances.extend([{'id':MID+':sample','template':'cardinality','parameters':{'object':'objects.groups','groups':True,'minimum':2},'severity':'hard'}, {'id':MID+':power','template':'min_detectable_effect','parameters':{'alpha':.05,'power':.8,'defer_threshold':.8},'severity':'soft'}, {'id':MID+':disclosure','template':'advisory','parameters':{'text':'Report sample size/exclusions, FDR over all fitted partitions of both hemispheres, effect size, d_min and site/scanner composition (or unavailable).'},'severity':'soft'}])
    rows=[]
    for instance in instances:
        value=evaluate(instance,env)
        rows.append({'constraint_id':instance['id'],'severity':instance['severity'],'template':instance['template'],'verdict':value['verdict'],'tool_observed':value,'source':[{'method_fact_id':MID+':'+('design' if ':design:' in instance['id'] else instance['id'].rsplit(':',1)[-1])}], 'on_fail':'block' if instance['severity']=='hard' else 'warn_and_disclose'})
    bypath={unwrap(f)['path']:unwrap(f) for f in files};issues=[]
    for key,labels in scope['labels'].items():
        ann=bypath.get(labels['annotation'],{});n=(ann.get('label')or{}).get('vertex_count');prefix=labels['annotation'].split('/label/')[0]+'/surf/'+key.rsplit('/',1)[-1]+'.'
        metrics=[f for p,f in bypath.items() if p.startswith(prefix) and f.get('format')=='surface_metric']
        if not n or not metrics or any((f.get('metric')or{}).get('vertex_count')!=n for f in metrics) or labels['cortex_label'] not in bypath:
            issues.append(key)
    rows.append({'constraint_id':MID+':identity','severity':'hard','verdict':'block' if issues else 'pass','tool_observed':{'reason':'Subject/hemisphere-bound native mesh cardinality and common registered dataset/species/atlas', 'issues':issues},'source':[{'method_fact_id':MID+':identity'}],'on_fail':'block'})
    return rows
