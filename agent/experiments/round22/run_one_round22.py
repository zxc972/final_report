import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path('/data/xuancheng/agent_v1')
BATCH = ROOT / 'retests/round22_20261024'
CASE = sys.argv[1]
IS_SYNTHETIC = CASE in ['S0', 'S0_retry']
QUESTIONS = {
    **{f'R22_G1_{i}': '这 20 名 IXI 被试，DKT 各分区平均皮层厚度与年龄的关系，控制性别。' for i in range(1,4)},
    **{f'R22_G2_{i}': '比较这 20 名 IXI 被试中男性和女性的 DKT 各分区平均皮层厚度。' for i in range(1,4)},
}
assert CASE in QUESTIONS
folder = BATCH / ('case_' + CASE)
folder.mkdir(exist_ok=False)
manifest_path = BATCH / 'authorization.json'
manifest = json.loads(manifest_path.read_text())
assert manifest['real_analysis_runs'] < manifest['rules']['model_requests_max_analysis_runs']
subject = 'IXI20'
catalog = json.loads((BATCH / 'catalog.ixi20.json').read_text())
input_roots = [row['path'] for row in catalog['roots']]
assert len(input_roots) == 20
assert {row['subject_id'] for row in catalog['roots']} == set(json.loads((Path('/data/xuancheng/datasets/provenance/round19_ixi_group_20261023') / 'data_registration.json').read_text())['subjects'])
user = 'env-smoke'
workspace = ROOT / 'workspaces' / user / 'output'
auth = json.loads((workspace.parent / '.auth.json').read_text())
ready = json.loads((BATCH / 'development_ready.json').read_text())
launch = json.loads((BATCH / 'development_launch.json').read_text())
instance = {'pid': ready['pid'], 'port': ready['port'], 'source_commit': launch['source_head']}
assert ready['C'] is False and ready['profile'] == 'product_graph_planner'
# New server deliberately inherits this existing access-token setting in memory.
process_env = dict(part.decode().split('=', 1) for part in Path('/proc/4144167/environ').read_bytes().split(b'\0') if b'=' in part)
access = process_env.get('PRIMX_ACCESS_TOKEN', '')
configuration = {}
for line in (ROOT / '.env').read_text().splitlines():
    line = line.strip().removeprefix('export ')
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=', 1)
        configuration[key.strip()] = value.strip().strip("\"'")
api_secret = next(configuration[k] for k in ['PLATFORM_API_KEY', 'INFERAI_API_KEY', 'OPENAI_API_KEY', 'API_KEY'] if configuration.get(k))
assert process_env['AGENT_CROSSSPECIES_RULES'] == '0'
assert process_env['ANALYSIS_MAX_MODEL_CALLS'] == '30'
assert process_env['ANALYSIS_MAX_TOOL_CALLS'] == '60'
assert process_env['ANALYSIS_MAX_EXECUTIONS'] == '8'
signing = hmac.new(access.encode(), auth['salt'].encode(), hashlib.sha256).hexdigest().encode()
encoded = base64.urlsafe_b64encode((user + ':' + str(int(time.time())+3600)).encode()).decode().rstrip('=')
user_token = encoded + '.' + hmac.new(signing, encoded.encode(), hashlib.sha256).hexdigest()
conversation = 'round22_'  + CASE + '_' + uuid.uuid4().hex
payload = {'message': QUESTIONS[CASE], 'mode': 'auto', 'provider': 'platform',
    'model': 'deepseek-v4-pro', 'conversationId': conversation, 'inputRoots': input_roots,
    'context': {'userId': user, 'workspaceDirectory': str(workspace), 'userToken': user_token,
        'species': 'human', 'threads': 2,
        'description': 'Analysis only; no preprocessing. Approved IXI20; AI follow-up retains IXI303/IXI542; IXI542 reviewed slices do not cover the orbitofrontal base. IXI442 screening flag retained. Claude AI initial and follow-up, not expert or blinded QC.'}}
public_request = {**payload, 'context': {k:v for k,v in payload['context'].items() if k != 'userToken'}}
(folder / 'request.public.json').write_text(json.dumps(public_request, ensure_ascii=False, indent=2) + '\n')
headers = {'Content-Type': 'application/json', 'X-User-Token': user_token, 'X-Round22-Case': CASE}
if access:
    headers['Authorization'] = 'Bearer ' + access
base = 'http://127.0.0.1:' + str(instance['port'])
started = time.monotonic()
stop = threading.Event()

def safe_write(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    assert api_secret not in text and user_token not in text
    if access:
        assert access not in text
    path.write_text(text + '\n')

def get_events(after=0):
    query = urllib.parse.urlencode({'userId': user, 'workspaceDirectory': str(workspace), 'after': after})
    request = urllib.request.Request(base + '/api/agent/analysis/' + conversation + '/events?' + query, headers=headers)
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)

def watch():
    last_seq = -1
    while not stop.wait(10):
        try:
            view = get_events()
            safe_write(folder / 'events_live.json', view)
            events = view.get('events', [])
            seq = view.get('last_seq', 0)
            if seq != last_seq:
                latest = events[-1] if events else {}
                print(json.dumps({'case': CASE, 'elapsed_seconds': round(time.monotonic()-started,1),
                    'events': len(events), 'last_seq': seq, 'stage': latest.get('stage'),
                    'status': latest.get('status'), 'title': latest.get('title')},ensure_ascii=False),flush=True)
                last_seq = seq
        except Exception:
            pass

thread = threading.Thread(target=watch, daemon=True)
thread.start()
result = {}
http_status = None
try:
    request = urllib.request.Request(base + '/api/agent/chat', data=json.dumps(payload,ensure_ascii=False).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(request, timeout=1800) as response:
        http_status = response.status
        result = json.load(response)
except urllib.error.HTTPError as error:
    http_status = error.code
    result = {'client_error': 'HTTPError', 'http_status': error.code}
    try:
        detail = json.loads(error.read())
        result['detail'] = detail
    except Exception:
        pass
except Exception as error:
    result = {'client_error': type(error).__name__}
finally:
    stop.set()
    thread.join(timeout=13)
safe_write(folder / 'agent_response.json', result)
events = []
after = 0
view = {}
try:
    while True:
        view = get_events(after)
        chunk = view.get('events', [])
        events.extend(chunk)
        if not view.get('has_more') or not chunk:
            break
        after = max(e['seq'] for e in chunk)
except Exception as error:
    view['fetch_error'] = type(error).__name__
view = {**view, 'events': events, 'has_more': False}
safe_write(folder / 'events_response.json', view)
with (folder / 'events.jsonl').open('w') as stream:
    for event in events:
        line = json.dumps(event,ensure_ascii=False)
        assert api_secret not in line and user_token not in line
        stream.write(line + '\n')
metadata = result.get('metadata', {})
validation = metadata.get('validation', {})
review = validation.get('internal_review', {})
summary = {'case': CASE, 'subject': subject, 'conversation_id': conversation,
    'model': payload['model'], 'http_status': http_status, 'status': metadata.get('status'),
    'overall_status': metadata.get('overall_status'), 'route': metadata.get('route'),
    'routing': metadata.get('routing'), 'model_calls': metadata.get('model_calls'),
    'tool_calls': metadata.get('tool_calls'), 'executions': metadata.get('executions'),
    'iterations': metadata.get('iterations'), 'elapsed_seconds': time.monotonic()-started,
    'public_output_contract': validation.get('public_output_contract'),
    'independent_numeric_status': validation.get('independent_numeric_status'),
    'independent_numeric': validation.get('independent_numeric'),
    'internal_review_decision': review.get('decision'), 'internal_review_protocol_valid': review.get('protocol_valid'),
    'phase_budget': metadata.get('phase_budget'), 'request_budget': metadata.get('requestBudget'),
    'event_count': len(events), 'run_id': metadata.get('run_id'),
    'output_directory': metadata.get('output_directory'),
    'source_commit': instance['source_commit'],
    'full_chain_passed': bool(metadata.get('status') == 'completed'
        and validation.get('public_output_contract',{}).get('status') == 'pass'
        and validation.get('independent_numeric_status') == 'pass'
        and review.get('decision') == 'pass' and review.get('protocol_valid') is True),
    'client_error': result.get('client_error')}
safe_write(folder / 'summary.json', summary)
manifest = json.loads(manifest_path.read_text())
manifest['status'] = 'finished_' + CASE
manifest['active_conversation'] = None
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['request_budget','independent_numeric','public_output_contract']},ensure_ascii=False),flush=True)
