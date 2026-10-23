from pathlib import Path
import ast
ROOT=Path('/data/xuancheng/agent_v1')
s=(ROOT/'retests/round19_20261023/run_one_round19.py').read_text()
s=s.replace('round19_20261023','round21_20261024').replace('X-Round19-Case','X-Round21-Case').replace("'round19_'","'round21_'")
start=s.index('QUESTIONS = {');end=s.index('\nassert CASE in QUESTIONS',start)
s=s[:start]+"QUESTIONS = {\n    **{f'R21_G1_{i}': '这 20 名 IXI 被试，DKT 各分区平均皮层厚度与年龄的关系，控制性别。' for i in range(1,4)},\n    **{f'R21_G2_{i}': '比较这 20 名 IXI 被试中男性和女性的 DKT 各分区平均皮层厚度。' for i in range(1,4)},\n}" +s[end:]
s=s.replace('pending QC IXI303/IXI542 and IXI442 screening flag retained. Claude AI preliminary review, not expert or blinded QC.','AI follow-up retains IXI303/IXI542; IXI542 reviewed slices do not cover the orbitofrontal base. IXI442 screening flag retained. Claude AI initial and follow-up, not expert or blinded QC.')
ast.parse(s)
(ROOT/'round21_source/agent/experiments/round21/run_one_round21.py').write_text(s)
print('driver prepared; no request sent')
