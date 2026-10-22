from pathlib import Path
import pytest
from backend.analysis_method_graph import MethodGraph
from backend.analysis_method_overlay import overlay,source_read

def test_overlay_and_unknown_id():
    graph=MethodGraph(Path(__file__).resolve().parents[4]/'knowledge/research_v13')
    card=graph.read('method:v14:group_regional_glm')
    assert card['method']['name']=='Group regional GLM'
    assert card['overlay_sha256']==overlay()[1]
    assert graph.read('method:v12:surface_annotation_roi')['method']['id']=='method:v12:surface_annotation_roi'
    with pytest.raises(ValueError,match='Unknown'):graph.read('method:v14:invented')
    assert source_read('METHOD_SOURCE_group_glm_v14',0,1000)['text'].startswith('Project')
