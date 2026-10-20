import json,tempfile
from pathlib import Path
from backend.analysis_validation import ArtifactValidator

def test_report_artifact_boundaries_and_strict_table_fields():
 with tempfile.TemporaryDirectory() as d:
  root=Path(d);report=root/'report.md';manifest=root/'analysis_manifest.json'
  def check(spec):
   manifest.write_text(json.dumps({'schema_version':'primatex.analysis_manifest.v1','artifacts':[spec]}));return ArtifactValidator().validate(root)
  report.write_text('# Methods\nActual observations only.\n',encoding='utf-8')
  assert check({'path':'report.md','kind':'markdown','min_chars':5})['passed']
  report.write_bytes(b'\xff\xfe\x00')
  assert not check({'path':'report.md','kind':'markdown'})['passed']
  report.write_text('   ')
  assert not check({'path':'report.md','kind':'text'})['passed']
  report.write_text('data')
  assert not check({'path':'report.md','kind':'text','required_keys':['methods']})['passed']
  (root/'table.tsv').write_text('a\tb\n1\t2\n')
  assert not check({'path':'table.tsv','kind':'tsv','required_keys':['a']})['passed']
  assert check({'path':'table.tsv','kind':'tsv','columns':['a','b'],'row_count':1})['passed']
