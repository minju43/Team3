import pytest
from visual.graph_view import GraphVisualizer
import json
import os

def test_graph_visualizer_parsing(tmp_path):
    # 테스트용 임시 JSON 파일 생성
    sample_data = {
        "num_nodes": 4,
        "edges": [
            {"source": 0, "target": 1, "weight": 1.0},
            {"source": 1, "target": 2, "weight": 2.0}
        ]
    }
    file_path = tmp_path / "preset_sample.json"
    file_path.write_text(json.dumps(sample_data), encoding='utf-8')

    # GraphVisualizer 로드 테스트
    viz = GraphVisualizer(str(file_path))
    assert viz.num_nodes == 4
    assert len(viz.edges) == 2
    
    summary = viz.get_graph_summary()
    assert summary["num_nodes"] == 4
    assert summary["edges"][0]["source"] == 0