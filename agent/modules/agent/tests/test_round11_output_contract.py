"""Public schema and identity errors are repairable without an oracle."""
import copy
import csv
import importlib
import io

import pytest
from test_analysis_agent import agent

public = importlib.import_module(agent.__package__ + '.analysis_output_contract')


def contract():
    group = {'labels': [{'key': 1, 'name': 'one'}, {'key': 2, 'name': 'two'}]}
    plan = {'method': {'method_id': 'method:v12:surface_annotation_roi'}, 'data': {'subjects': ['fixture']}, 'analysis_scope': {'labels': {'fixture/lh': group}}}
    ops = {'calls': [{'function': 'parcel_summary', 'scope': 'fixture/lh', 'inputs': {'metric_path': '/inputs/0/surf/lh.thickness'}}]}
    return public.table_contract(plan, ops)


def rows():
    return [{'subject': 'fixture', 'hemisphere': 'lh', 'metric': 'thickness', 'label_key': k,
             'name': name, 'vertex_count': 3, 'mean': 1.234567891234, 'std_population': 0.123456789123,
             'median': 1.234567891234, 'zero_count': 0, 'units': 'stored; software mm, scale unverified'} for k, name in [(1, 'one'), (2, 'two')]]


def raw(values, columns=None):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns or list(values[0]), extrasaction='ignore')
    writer.writeheader()
    writer.writerows(values)
    return stream.getvalue().encode()


def test_complete_public_schema():
    c = contract()
    assert c['fixed_values']['metric'] == 'thickness'
    assert c['columns']['label_key'] == 'int' and c['columns']['mean'] == 'float'
    assert c['expected_rows'] == 2 and c['alias_mapping'] is False
    assert public.validate_csv(raw(rows()), c)['status'] == 'pass'


@pytest.mark.parametrize('fault', ['metric', 'identity', 'name', 'rows', 'column', 'type', 'nonfinite', 'duplicate'])
def test_public_faults_are_specific_and_never_aliased(fault):
    values = copy.deepcopy(rows())
    columns = None
    if fault == 'metric':
        values[0]['metric'] = 'cortical_thickness'
    elif fault == 'identity':
        values[0]['label_key'] = 99
    elif fault == 'name':
        values[0]['name'] = 'wrong'
    elif fault == 'rows':
        values = values[:1]
    elif fault == 'column':
        columns = [key for key in values[0] if key != 'mean']
    elif fault == 'type':
        values[0]['vertex_count'] = 1.5
    elif fault == 'nonfinite':
        values[0]['mean'] = float('nan')
    else:
        values.append(values[0])
    result = public.validate_csv(raw(values, columns), contract())
    assert result['status'] == 'fail' and result['errors']
    assert result['numeric_mismatch_count'] == 0
    if fault == 'metric':
        assert "use ['thickness']" in str(result['errors'])
        assert values[0]['metric'] == 'cortical_thickness'
        assert result['identity_mismatch_count'] == 2


def test_independent_counts_have_distinct_meanings():
    numeric = importlib.import_module(agent.__package__ + '.analysis_independent_numeric')
    expected = [{'id': 'one', 'mean': 1.0}, {'id': 'two', 'mean': 2.0}]
    actual = [{'id': 'one', 'mean': 1.1}, {'id': 'other', 'mean': 2.0}]
    result = numeric.compare_rows(expected, actual, ['id'], ['mean'])
    assert result['identity_mismatch_count'] == 2
    assert result['numeric_mismatch_count'] == 1
    assert result['mismatch_count'] == 3


def test_public_contract_feedback_precedes_host_reference(tmp_path, monkeypatch):
    from test_round8_closure import sealed, fake_execution
    import json
    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    good = tools.executor
    host = importlib.import_module(agent.__package__ + '.analysis_independent_numeric')
    seen = []
    monkeypatch.setattr(host, 'verify', lambda value: seen.append('host_after_contract'))
    class Executor:
        def run(self, script, **kwargs):
            result = good.run(script, **kwargs)
            if 'wrong_metric' in script.read_text():
                path = tools.workdir / 'summary.csv'
                path.write_text(path.read_text().replace('thickness', 'cortical_thickness'))
            return result
    tools.executor = Executor()
    tools.write_code('/work/analysis.py', '# wrong_metric')
    first = tools.run_python()
    assert first['exit_code'] == 0 and first['state']['phase'] == 'executed_failed'
    assert seen == []
    feedback = json.loads((tools.workdir/'tool_results/validation_feedback.json').read_text())
    assert feedback['public_output_contract']['identity_mismatch_count'] > 0
    assert 'thickness' in str(feedback) and 'expected' not in str(feedback.get('private', {}))
    tools.write_code('/work/analysis.py', '# corrected public contract')
    second = tools.run_python()
    assert second['state']['phase'] == 'finalized'
    assert seen == ['host_after_contract']


def test_integer_identity_serialization_is_publicly_unambiguous():
    values=rows()
    values[0]['label_key']='1.0'
    result=public.validate_csv(raw(values),contract())
    assert result['status']=='fail'
    assert 'label_key must be finite int' in str(result['errors'])
