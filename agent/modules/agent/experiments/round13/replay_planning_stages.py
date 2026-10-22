"""Replay real historical initial contexts through an offline real ToolNode."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

root = Path('/data/xuancheng/agent_round13_trial_20261022')
sys.path.insert(0, str(root / 'backend_review/tests'))
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import PrivateAttr
from pytest import MonkeyPatch

cases = [
    ('R11B_P1_1', Path('/data/xuancheng/agent_round11_trial_20261022/trials/R11B_P1_1')),
    ('R11B_P1_2', Path('/data/xuancheng/agent_round11_trial_20261022/trials/R11B_P1_2')),
    ('R12B_P1_1', Path('/data/xuancheng/agent_round12_trial_20261022/cohort_b/trials/R12B_P1_1')),
    ('R12B_P1_2', Path('/data/xuancheng/agent_round12_trial_20261022/cohort_b/trials/R12B_P1_2')),
]
results = []
for case, folder in cases:
    source = next(path for path in sorted(folder.glob('http_*.json'))
                  if json.loads(path.read_text())['request'].get('tools'))
    original = json.loads(source.read_text())['request']['messages']
    original = [item for item in original if item['role'] in {'user', 'system'}]
    observations = []
    with tempfile.TemporaryDirectory(dir=root / 'tmp') as temporary, MonkeyPatch.context() as patch:
        tools = setup_products(Path(temporary), patch)
        patch.setenv('ANALYSIS_ENABLE_INTERNAL_REVIEW', '0')
        class Replay(BaseChatModel):
            _calls: int = PrivateAttr(default=0)
            @property
            def _llm_type(self):
                return 'offline-exposure-replay'
            def bind_tools(self, tools, **kwargs):
                return self.bind(exposed=[item.name if not isinstance(item, dict) else item.get('name') for item in tools], choice=kwargs.get('tool_choice'))
            def get_num_tokens(self, text):
                return max(1, len(text)//4)
            def get_num_tokens_from_messages(self, messages, tools=None):
                return sum(self.get_num_tokens(str(item.content)) for item in messages)
            def _generate(self, messages, **kwargs):
                i = self._calls
                self._calls += 1
                observations.append({'call': i+1, 'tools': sorted(kwargs['exposed']), 'tool_choice': kwargs.get('choice')})
                if i < 4:
                    assert set(kwargs['exposed']) == {'ls', 'read_file', 'read_operations', 'plan_analysis'}
                    name, arguments = 'ls', {'path': '/inputs/0'}
                elif i == 4:
                    assert kwargs['exposed'] == ['plan_analysis']
                    assert kwargs['choice']['function']['name'] == 'plan_analysis'
                    name, arguments = 'plan_analysis', {'intent': {'measures': ['thickness'], 'regions': 'aparc'}}
                elif i in {5, 6}:
                    expected = {'commit_plan', 'plan_analysis', 'read_operations'} if i == 5 else {'commit_plan', 'plan_analysis'}
                    assert set(kwargs['exposed']) == expected
                    assert kwargs['choice']['function']['name'] == 'commit_plan'
                    saved = tools.control_store.latest('planning_result')['record']['candidates'][0]
                    name, arguments = 'commit_plan', {'candidate_id': 12 if i == 5 else saved['candidate_id'], 'rationale': 'Synthetic engineering replay', 'code_path': 'replay.py'}
                elif i == 7:
                    assert set(kwargs['exposed']) == {'write_code', 'run_python', 'read_operations', 'finalize_artifacts'}
                    assert kwargs['choice']['function']['name'] == 'write_code'
                    name, arguments = 'write_code', {'path': '/work/replay.py', 'code': "print('synthetic exposure only')\n"}
                else:
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content='Offline tool exposure replay ended; no image computation.'))])
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content='', tool_calls=[{'id': 'replay-'+str(i), 'name': name, 'args': arguments}]))])
        model = Replay()
        graph = agent._build_coding_agent(tools, model='offline', base_url='https://example.invalid/v1', api_key='fixture', model_factory=lambda **kwargs: model)
        graph.invoke({'messages': original}, {'recursion_limit': 120, 'configurable': {'thread_id': case+'-offline'}})
        assert tools.session.record['planning_read_calls'] == 4
        assert tools.executions == 0
        results.append({'case': case, 'source': str(source), 'source_http_file_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'initial_messages_sha256': hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest(),
                        'actual_real_toolnode_bindings': observations, 'planning_reads': 4, 'image_executions': 0,
                        'network_calls': 0, 'passed': True,
                        'scope': 'Historical contexts, scripted fake model, synthetic input bundle; registry/quota/argument recovery only, not model efficacy'})
(root / 'audit/planning_stage_replays.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
print(json.dumps({'historical_contexts': len(results), 'passed': all(item['passed'] for item in results), 'provider_calls': 0}))
