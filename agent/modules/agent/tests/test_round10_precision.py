"""Public precision gate without a private answer or tolerance adjustment."""
import importlib
from test_analysis_agent import agent

precision=importlib.import_module(agent.__package__+".analysis_precision")


def test_rounding_and_full_precision_are_distinguished():
    low=b"mean,std_population,median\n1.234568,0.123457,1.111111\n2.234568,0.234568,2.111111\n"
    assert precision.rounded_columns(low,["mean","std_population","median"],True)==["mean","std_population","median"]
    full=b"mean,std_population,median\n1.234567891234567,0.123456789123456,1.111111112345678\n"
    assert precision.rounded_columns(full,["mean","std_population","median"],True)==[]
    assert precision.rounded_columns(low,["mean"],False)==[]
    mixed=b"mean,std_population,median\n1.234567891234567,0,1.234567891234567\n"
    assert precision.rounded_columns(mixed,["mean","std_population","median"],True)==[]


def test_rounding_returns_to_failed_and_full_precision_finalizes(tmp_path,monkeypatch):
    from test_round8_closure import sealed,fake_execution
    tools,_,_=sealed(tmp_path,monkeypatch)
    fake_execution(tools)
    monkeypatch.setattr(precision,"check_precision",lambda *args: [
        {"status":"warn","message":"numeric output appears rounded",
         "file":"summary.csv","columns":["mean"]}
    ])
    tools.write_code("/work/analysis.py","print('fixture')")
    tools.run_python()
    assert tools.session.state()["phase"]=="executed_failed"
    assert "numeric output appears rounded" in tools.session.record["missing"][0]
    refused=tools.finalize_artifacts([{"path":"summary.csv","kind":"csv"}])
    assert refused["status"]=="error" and "execute" in refused["error"]
    monkeypatch.setattr(precision,"check_precision",lambda *args: [])
    tools.write_code("/work/analysis.py","print('full precision fixture')")
    tools.run_python()
    assert tools.session.state()["phase"]=="finalized"
