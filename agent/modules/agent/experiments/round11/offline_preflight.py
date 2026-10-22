"""Offline data/planning/identity check before the bounded Round 11 server."""
from pathlib import Path
import json
import os
import shutil
import sys

D=Path("/data/xuancheng/agent_round11_trial_20261022")
OLD=Path("/data/xuancheng/agent_round7_trial_20261021")
for name in ["private_reference","stage0","trials"]:
    (D/name).mkdir(exist_ok=True)
for name in ["recomputed_reference.json","p1_acceptance_contract.json","hull_reference.json","hull_acceptance_contract.json"]:
    shutil.copy2(OLD/"private_reference"/name,D/"private_reference"/name)
roots=[Path("/data/xuancheng/featurize_20261011/data/KM002/KM002"),
       *[Path("/data/xuancheng/human_fastsurfer/subjects")/n for n in ["100610","101309","101410"]]]
catalog={"roots":[{"path":str(root),"subject_id":root.name,
    "species_declared":"monkey_unknown"if i==0 else"human","species_verified":None,
    "source":"User-approved registration; no independent species verification"}for i,root in enumerate(roots)]}
(D/"data_catalog.json").write_text(json.dumps(catalog,indent=2)+"\n")
os.environ.update(AGENT_CROSSSPECIES_RULES="0",AGENT_KNOWLEDGE_PROFILE="product_graph_planner",AGENT_DATA_CATALOG=str(D/"data_catalog.json"),
    AGENT_ANALYSIS_STATE_DIR=str(D/"offline_state"),AGENT_RESEARCH_EVIDENCE_ROOT="/data/xuancheng/agent_overnight_20261020/research_evidence_v13",
    AGENT_SOURCE_GRAPH_ROOT="/data/xuancheng/agent_overnight_20261020/software_graph",PYTHONDONTWRITEBYTECODE="1")
sys.path.insert(0,str(D/"backend_review"))
from backend.analysis_agent import AnalysisTools
from backend.analysis_executor import SandboxExecutor
from backend.analysis_knowledge import KnowledgeStore
from backend.analysis_product_planner import plan_analysis,commit_candidate
work=D/"offline_work";work.mkdir(exist_ok=True)
tools=AnalysisTools(work,roots,SandboxExecutor(work,roots),KnowledgeStore(),"",workspace=work)
results={}
for name,intent in [
    ("P1",{"measures":["thickness"],"regions":"aparc","subjects":["KM002"]}),
    ("P2",{"measures":["lgi"],"regions":"global","subjects":["KM002"],"species":"macaque","space":"native"}),
]:
    result=plan_analysis(tools,intent)
    (D/"stage0"/("offline_"+name+".json")).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    results[name]=result
    print(name,"candidates",[(c["method"]["method_id"],c["label_counts"])for c in result["candidates"]],
          "infeasible",[c.get("reason")for c in result["infeasible"]],flush=True)
assert any(set(c["label_counts"].values())=={33}for c in results["P1"]["candidates"])
assert any("MATLAB"in c.get("reason","")for c in results["P2"]["infeasible"])
assert any(c["method"]["method_id"].endswith("global_convex_hull_gyrification")for c in results["P2"]["candidates"])
candidate=next(c for c in results["P1"]["candidates"]if c["atlas"]["name"]=="aparc")
committed=commit_candidate(tools,candidate["candidate_id"],"Offline engineering check only","/work/preflight.py")
assert committed["status"]=="committed"
card=tools.model_context.offload("commit_plan",committed)
(D/"stage0/execution_card.json").write_text(json.dumps(card,ensure_ascii=False,indent=2)+"\n")
assert len(card["execution_card"])<=2200
(D/"stage0/offline_P1_commit.json").write_text(json.dumps(committed,ensure_ascii=False,indent=2)+"\n")
tests=json.loads((D/"audit/final_checks.json").read_text())
assert all(r["exit_code"]==0 for r in tests.values())
(D/"audit/preflight_tests.json").write_text(json.dumps({k:v["exit_code"]for k,v in tests.items()},indent=2)+"\n")
(D/"stage0/offline_ready.json").write_text(json.dumps({"passed":True,"model_requests":0,"physical_scale_verified":False},indent=2)+"\n")
shutil.copy2(D/"backend_review/knowledge_analysis/experiment_budget.json",D/"experiment_budget.json")
assert not(D/"provider_budget.json").exists()
print("Offline ready; no model requests made")

