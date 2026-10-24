"""Per-question stop rules, using only observed terminal outcomes."""

def decision(summaries):
    summaries=sorted(summaries,key=lambda row:row['case'])
    categories=[row.get('failure_classification') or {} for row in summaries]
    if sum(c.get('category')=='system_defect' for c in categories)>=2:
        return {'stop':True,'reason':'same_question_two_system_defects','observed_cases':[r['case'] for r in summaries]}
    if len(categories)>=2:
        a,b=categories[-2:]
        if a.get('stop_eligible') and b.get('stop_eligible') and a.get('category')==b.get('category'):
            return {'stop':True,'reason':'consecutive_same_question_failure_chain','category':b['category'],'observed_cases':[r['case'] for r in summaries]}
    return {'stop':len(summaries)>=3,'reason':'three_run_limit' if len(summaries)>=3 else 'continue','observed_cases':[r['case'] for r in summaries]}
