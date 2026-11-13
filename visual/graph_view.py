# visual/graph_view.py
import json
import networkx as nx
import matplotlib.pyplot as plt
from typing import Dict, Any, List

class GraphVisualizer:
    """
    Max-Cut 문제의 프리셋 JSON 데이터를 파싱하고, 
    시각화(NetworkX / Plotly 또는 Streamlit 연동)를 위한 뼈대를 제공하는 클래스
    """
    def __init__(self, json_file_path: str = None):
        self.raw_data: Dict[str, Any] = {}
        self.num_nodes: int = 0
        self.edges: List[Dict[str, Any]] = []
        
        if json_file_path:
            self.load_preset_json(json_file_path)

    def load_preset_json(self, file_path: str) -> None:
        """프리셋 JSON 파일을 로드하여 노드 수와 엣지 정보를 파싱합니다."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.raw_data = json.load(f)
            
            # JSON 구조에 따른 키 값 매핑 (필요시 데이터셋 형식에 맞춰 조절)
            self.num_nodes = self.raw_data.get("num_nodes", 0)
            self.edges = self.raw_data.get("edges", [])
        except FileNotFoundError:
            print(f"[Error] 프리셋 파일을 찾을 수 없습니다: {file_path}")
        except json.JSONDecodeError:
            print(f"[Error] JSON 파싱 중 오류가 발생했습니다: {file_path}")

    def get_graph_summary(self) -> Dict[str, Any]:
        """렌더링 전 그래프의 기본 통계 요약 반환"""
        return {
            "num_nodes": self.num_nodes,
            "num_edges": len(self.edges),
            "edges": self.edges
        }

    def render_graph_placeholder(self) -> None:
        """
        [T20-1 기본 렌더링 틀]
        Streamlit이나 대시보드 UI에 그래프 렌더링 영역을 할당하기 위한 뼈대 메서드
        """
        summary = self.get_graph_summary()
        print(f"=== [Graph View Framework] ===")
        print(f"총 노드 수: {summary['num_nodes']}개")
        print(f"총 엣지 수: {summary['num_edges']}개")
        print("그래프 렌더링 틀 준비 완료.")
    def draw_weighted_graph(self):
        """
        [T20-2] 엣지의 가중치를 선의 두께와 색상으로 시각화하는 메서드
        (Streamlit이나 대시보드에 넘겨줄 Figure 객체를 반환합니다)
        """
        G = nx.Graph()
        G.add_nodes_from(range(self.num_nodes))
        
        for edge in self.edges:
            G.add_edge(edge['source'], edge['target'], weight=edge.get('weight', 1.0))
            
        # 노드 위치 고정 (매번 모양이 바뀌지 않도록 seed 설정)
        pos = nx.spring_layout(G, seed=42) 
        
        # 가중치 리스트 추출
        weights = [G[u][v]['weight'] for u, v in G.edges()]
        
        fig, ax = plt.subplots(figsize=(8, 6))
        
        # 노드 렌더링
        nx.draw_networkx_nodes(G, pos, node_color='lightblue', node_size=700, ax=ax)
        nx.draw_networkx_labels(G, pos, font_family="sans-serif", ax=ax)
        
        # 엣지 렌더링 (가중치 비례 두께 및 색상 매핑)
        nx.draw_networkx_edges(
            G, pos, 
            width=[w * 2 for w in weights], # 선 두께 
            edge_color=weights,             # 선 색상 
            edge_cmap=plt.cm.Reds,          # 붉은색 그라데이션
            ax=ax
        )
        
        ax.set_title("Party Conflict (Max-Cut) - Weight Visualization")
        ax.axis('off')
        
        return fig
    def draw_partitioned_graph(self, partition_bitstring: str):
        """
        [T20-3] Max-Cut 2분할 결과(비트스트링)를 받아 노드를 A/B 그룹으로 나누어 하이라이트하는 메서드
        """
        G = nx.Graph()
        G.add_nodes_from(range(self.num_nodes))
        
        for edge in self.edges:
            G.add_edge(edge['source'], edge['target'], weight=edge.get('weight', 1.0))
            
        # 노드 위치 고정 (동일한 형태 유지)
        pos = nx.spring_layout(G, seed=42) 
        
        # 비트스트링 값(0 또는 1)에 따라 노드 색상 그룹 분류
        node_colors = []
        for i in range(self.num_nodes):
            # 비트스트링 인덱스가 '1'이면 파란색(B그룹), '0'이면 붉은색(A그룹)
            if i < len(partition_bitstring) and partition_bitstring[i] == '1':
                node_colors.append('royalblue')
            else:
                node_colors.append('tomato')
                
        fig, ax = plt.subplots(figsize=(8, 6))
        
        # 노드 렌더링 (A/B 그룹 색상 적용)
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=700, ax=ax)
        
        # 가독성을 위해 노드 번호 색상을 흰색으로 변경
        nx.draw_networkx_labels(G, pos, font_family="sans-serif", font_color="white", ax=ax)
        
        # 엣지 렌더링 (노드 그룹 구분을 강조하기 위해 선 색상은 회색으로 통일)
        weights = [G[u][v]['weight'] for u, v in G.edges()]
        nx.draw_networkx_edges(
            G, pos, 
            width=[w * 1.5 for w in weights], 
            edge_color='gray',          
            alpha=0.5,
            ax=ax
        )
        
        ax.set_title(f"Max-Cut Partition Highlight (Result: {partition_bitstring})")
        ax.axis('off')
        
        return fig