import importlib
import json
from pathlib import Path
import pytest
from test_analysis_agent import agent
from test_analysis_evidence import gateway

def test_registered_source_path_in_software_key_is_an_opaque_id(monkeypatch):
    ev = importlib.import_module(agent.__package__ + '.analysis_evidence')
    adapter, stores = gateway(monkeypatch)
    native = 'InputSpec:nipype/interfaces/freesurfer/utils.py:in_file'
    identifier = ev.evidence_id('software_contract', native)
    assert '/' not in identifier and identifier.startswith('software_contract:~')
    assert ev.split_evidence_id(identifier) == ('software_contract', native)
    result = adapter.read(identifier)
    assert result['id'] == identifier
    assert stores.calls[-1] == ('software_read', native)
    for raw in ['software_contract:../secret', 'software_contract:/etc/passwd', 'software_contract:bad/key', 'source_text:/etc/passwd']:
        with pytest.raises(ValueError): ev.split_evidence_id(raw)
    with pytest.raises(ValueError): ev.evidence_id('software_contract', '/etc/passwd')

def test_runtime_inventory_fits_transport_under_verbose_help(monkeypatch):
    import contextlib
    import io
    import os
    import shutil
    import subprocess
    from types import SimpleNamespace
    module = importlib.import_module(agent.__package__ + '.analysis_executor')
    real_isfile = os.path.isfile
    monkeypatch.setattr(shutil, 'which', lambda name: '/synthetic/bin/' + name)
    monkeypatch.setattr(os.path, 'isfile', lambda path: str(path).startswith('/synthetic/bin/') or real_isfile(path))
    real_access = os.access
    monkeypatch.setattr(os, 'access', lambda path, mode: True if str(path).startswith('/synthetic/bin/') else real_access(path, mode))
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='Verbose help ' + 'x' * 4000, stderr=''))
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(module._runtime_inventory_code(), '<trusted-inventory>', 'exec'), {})
    text = output.getvalue()
    assert len(text.encode()) < 16000
    result = json.loads(text.split('PRIMATEX_RUNTIME_INVENTORY=', 1)[1])
    assert result['commands']['matlab']['executable'] is True
    assert result['commands']['wb_command']['executable'] is True
    assert all(row['excerpt_truncated'] for row in result['commands'].values())
    assert all(len(row['stdout_excerpt']) <= 120 for row in result['commands'].values())

def test_mris_info_exact_nonzero_version_policy(monkeypatch):
    import os
    import shutil
    import subprocess
    from types import SimpleNamespace
    software = importlib.import_module(agent.__package__ + '.analysis_software')
    real_isfile = os.path.isfile
    real_access = os.access
    monkeypatch.setattr(shutil, 'which', lambda name: '/synthetic/bin/' + name)
    monkeypatch.setattr(os.path, 'isfile', lambda path: str(path).startswith('/synthetic/bin/') or real_isfile(path))
    monkeypatch.setattr(os, 'access', lambda path, mode: True if str(path).startswith('/synthetic/bin/') else real_access(path, mode))
    namespace = {}
    exec(compile(software.PROBE_SOURCE, '<fixed-software-probe>', 'exec'), namespace)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout='7.2.0\n', stderr=''))
    observed = namespace['probe_command']('mris_info')
    assert observed['exit_code'] == 1 and observed['executable'] is True
    assert observed['accepted_nonzero_version_exit'] is True
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout='', stderr='FREESURFER_HOME undefined'))
    assert namespace['probe_command']('mris_info')['executable'] is False

