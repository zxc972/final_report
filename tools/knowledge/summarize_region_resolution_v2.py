"""Summarize unchanged resolver outputs, with subject as the reporting unit."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,statistics
from collections import defaultdict
from pathlib import Path


def distribution(values):
    values=sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not values:return {'n':0}
    def percentile(q):
        x=(len(values)-1)*q;i=int(x);j=min(i+1,len(values)-1)
        return values[i]+(x-i)*(values[j]-values[i])
    return {'n':len(values),'min':values[0],'q25':percentile(.25),'median':statistics.median(values),'q75':percentile(.75),'max':values[-1],'mean':statistics.mean(values)}


def summarize(source):
    data=json.loads(source.read_text(encoding='utf-8'));results=data['results']
    exact_groups=defaultdict(lambda:defaultdict(list));dice_groups=defaultdict(list);errors=[];theta_groups=defaultdict(list)
    for item in results:
        condition=item['condition'];subject=item['provenance']['subject'];hemi=item['provenance']['hemi'];cohort='fsaverage' if subject=='fsaverage' else 'IXI20'
        for method,record in item['methods'].items():
            if 'exact' in record:
                exact_groups[(condition,method,cohort)][subject].append(record['exact'])
                errors.extend({'condition':condition,'method':method,'cohort':cohort,'subject':subject,'hemisphere':hemi,'error':e} for e in record['exact']['errors'])
            if condition.startswith('C3'):
                dice_groups[(condition,method,cohort)].extend(v['dice'] for v in record['geometry'].values())
        for row in item['theta_sweep']:theta_groups[(condition,cohort,row['theta'])].append(row)
    accuracy=[]
    for (condition,method,cohort),subjects in sorted(exact_groups.items()):
        per_subject={s:sum(r['accuracy']*r['n_labels'] for r in rs)/sum(r['n_labels'] for r in rs) for s,rs in subjects.items()}
        accuracy.append({'condition':condition,'method':method,'cohort':cohort,'subject_accuracy':per_subject,'distribution':distribution(per_subject.values()),'errors':sum(len(r['errors']) for rs in subjects.values() for r in rs)})
    dice=[{'condition':c,'method':m,'cohort':h,'distribution':distribution(v)} for (c,m,h),v in sorted(dice_groups.items())]
    agreement=defaultdict(lambda:defaultdict(list))
    for row in data['stability']:
        assert row['anchor']=='fsaverage'
        agreement[row['condition']][row['subject']].append(row['agreement'])
    stability=[{'condition':c,'method':'overlap_weighted','anchor':'fsaverage','subject_mean_hemisphere_agreement':{s:statistics.mean(v) for s,v in ss.items()},'distribution':distribution(statistics.mean(v) for v in ss.values())} for c,ss in sorted(agreement.items())]
    theta=[]
    for (condition,cohort,level),rows in sorted(theta_groups.items()):
        theta.append({'condition':condition,'cohort':cohort,'theta':level,'accuracy':distribution(r.get('accuracy') for r in rows),'mean_dice':distribution(r['mean_dice'] for r in rows),'unassigned':sum(r['unassigned'] for r in rows),'resolved_regions':sum(r['resolved'] for r in rows)})
    return {'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'subjects':21,'template':'fsaverage','development_subjects':20,'skipped':data['skipped'],'parameters':data['parameters'],'units':{'accuracy':'both hemispheres combined, weighted by label count, then 20 subject median/min','C3_Dice':'each hemisphere x coarse region; fsaverage12 and IXI20 240 observations per method','stability':'original runner weighted mapping agreement; hemispheres averaged within subject, then subject distribution','theta':'original frozen weighted resolver sensitivity; hemisphere-level distributions; no parameter selection'},'accuracy':accuracy,'errors':errors,'C3_dice':dice,'stability':stability,'theta_sensitivity':theta,'model_calls':0}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True,type=Path);parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
    result=summarize(args.source);args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'region_resolution_aggregate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,key in [('accuracy','accuracy'),('dice','C3_dice'),('stability','stability')]:
        rows=[{**{k:v for k,v in r.items() if k in ['condition','method','cohort','anchor','errors']},**r['distribution']} for r in result[key]]
        fields=list(dict.fromkeys(k for r in rows for k in r))
        with (args.out/(name+'.csv')).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    print(json.dumps({'accuracy':[(r['condition'],r['method'],r['cohort'],r['distribution']['median'],r['distribution']['min'],r['errors']) for r in result['accuracy']],'C3_Dice':[(r['method'],r['cohort'],r['distribution']['median'],r['distribution']['min']) for r in result['C3_dice']],'stability':[(r['condition'],r['distribution']['median'],r['distribution']['min']) for r in result['stability']]},ensure_ascii=False))
if __name__=='__main__':main()
