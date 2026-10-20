"""Start loopback-only GUI services against the existing coding backend.

Run with modules/agent/.venv-coding/bin/python. No credentials are printed.
The agent must first be started with start-coding-backend.sh.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / 'modules/agent'
STATE = AGENT / '.analysis_service'
FRONT = ROOT / 'modules/gui/monkey-brain-frontend'
NODE = ROOT / '.refactor_tools/node-v22.14.0-linux-x64/bin/node'

def listening(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(('127.0.0.1', port)) == 0

def main():
    pid = int((STATE / 'coding-backend.pid').read_text().strip())
    proc = Path('/proc') / str(pid)
    command = (proc / 'cmdline').read_bytes()
    if b'uvicorn' not in command or Path(os.readlink(proc / 'cwd')) != AGENT:
        raise SystemExit('Recorded PID is not this coding backend; update coding-backend.pid.')
    backend_env = dict(item.split('=', 1) for item in (proc / 'environ').read_bytes().decode().split('\0') if '=' in item)
    env = os.environ.copy()
    for name in ('PRIMX_ACCESS_TOKEN', 'AGENT_DEFAULT_WORKSPACE', 'PRIMX_FILE_ROOT'):
        env.pop(name, None)
        if name in backend_env:
            env[name] = backend_env[name]
    agent_port = int(backend_env.get('AGENT_PORT', '8110'))
    headers = {'Authorization': 'Bearer ' + env['PRIMX_ACCESS_TOKEN']} if env.get('PRIMX_ACCESS_TOKEN') else {}
    request = urllib.request.Request(f'http://127.0.0.1:{agent_port}/api/agent/analysis/health', headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        assert json.load(response)['dependenciesReady']
    env.update(PIPELINE_PORT='8000', PIPELINE_HOST='127.0.0.1', AGENT_PORT=str(agent_port), VITE_DEV_HOST='127.0.0.1', VITE_DEV_PORT='8080')
    for name in ('VITE_PIPELINE_API', 'VITE_AGENT_BACKEND_URL', 'VITE_AGENT_BACKEND_PORT'):
        env.pop(name, None)
    ports = FRONT / 'public/ports.json'
    backup = STATE / 'ports.before-coding-web.json'
    if not backup.exists():
        backup.write_bytes(ports.read_bytes())
    ports.write_text(json.dumps({'pipelinePort':'8000', 'agentPort':str(agent_port), 'frontendPort':'8080', 'sameOriginApi':True}, indent=2) + '\n')
    services = [
        ('coding-pipeline', 8000, [str(NODE), str(ROOT / 'modules/gui/monkey-brain-backend/server.js')]),
        ('coding-frontend', 8080, [str(NODE), str(FRONT / 'node_modules/vite/bin/vite.js')]),
    ]
    for name, port, command in services:
        if listening(port):
            raise SystemExit(f'Port {port} already listening; inspect it before starting again.')
    for name, port, command in services:
        with (STATE / (name + '.log')).open('ab') as log:
            child = subprocess.Popen(command, cwd=FRONT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        (STATE / (name + '.pid')).write_text(str(child.pid) + '\n')
        for _ in range(30):
            if listening(port):
                break
            if child.poll() is not None:
                raise SystemExit(f'{name} exited; inspect its log.')
            time.sleep(0.2)
        else:
            raise SystemExit(f'{name} failed to listen; inspect its log.')
        print(f'{name}: 127.0.0.1:{port}, PID {child.pid}')
    print(f'Proxy: /api/agent -> {agent_port}; /api -> 8000; loopback only.')

if __name__ == '__main__':
    main()
