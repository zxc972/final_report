"""Group result scope and required report disclosures; no reference values exposed."""
import copy,re

REQUIRED={
 'sample size':r'(?i)(sample\s*size|\bn\s*=|样本量)',
 'excluded subjects':r'(?i)(exclud|排除)',
 'FDR family':r'(?i)(FDR|Benjamini|BH\b)',
 'effect size':r'(?i)(effect[_\s-]*size|cohen|pearson|partial_r|效应量)',
 'd_min':r'(?i)(d_min|dmin|最小可检测效应)',
 'site/scanner composition':r'(?i)(site|scanner|站点|扫描仪)',
}


def missing_disclosures(text):
    return [name for name,pattern in REQUIRED.items() if not re.search(pattern,text)]


def enforce_report_review(review,card,workdir):
    if not card.get('group_report_requirements'):return review
    from .analysis_internal_review import bounded_file
    path=workdir/'report.md'
    text=bounded_file(workdir,path,8*1024*1024).decode('utf-8-sig','replace') if path.is_file() else ''
    missing=missing_disclosures(text)
    if not missing:return review
    result=copy.deepcopy(review);result['decision']='revise'
    result['findings']=result.get('findings',[])[:5]+[{'severity':'blocking','claim':'Required group report disclosures are missing','observation':'Missing: '+', '.join(missing),'evidence_files':['report.md'],'question':'Add sample size/exclusions, FDR family, effect size, d_min and site/scanner composition (or explicitly unavailable), then rerun.'}]
    return result


def conclusion(tools,text,checks,numeric):
    from .analysis_crossspecies import conclusion_card
    from .analysis_crossspecies_templates import min_detectable_effect
    plan=tools.control_store.latest('plan')['record']['plan'];scope=plan['analysis_scope']
    private=tools.control_store.latest('independent_numeric_private')
    rows=private['record'].get('expected',{}).get('group_results.csv',[]) if private else []
    fitted=[row for row in rows if row.get('status')=='ok']
    negative=bool(fitted) and all(row['q_fdr']>=.05 for row in fitted) and numeric.get('status')=='pass'
    power=min_detectable_effect({'alpha':.05,'power':.8,'defer_threshold':.8},{'group_inference':True,'group_design':scope,'negative_result':negative})
    checks=[row for row in checks if row['constraint_id']!='method:v14:group_regional_glm:power']+[
      {'constraint_id':'method:v14:group_regional_glm:power','severity':'soft','verdict':power['verdict'],'tool_observed':power}]
    return conclusion_card(text or 'No Agent interpretation was supplied.','group_inference',checks,{'independent_numeric':numeric},['group_inference'])
