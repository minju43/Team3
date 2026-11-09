# Q-PartyCut (Max-Cut with QAOA & Error Mitigation)

---

## 1. 프로젝트 진행 현황 (Sprint 1 완료)

- **US-01: 갈등 그래프 QUBO 수식 변환**
  - 인접 행렬 및 그래프 유효성 검증기 (`validator.py`)
  - Pauli-Z 연산자 기반 Ising 비용 해밀토니안 생성기 (`hamiltonian.py`)
- **US-02: QAOA 최적화 루프 구축**
  - 레이어($p$) 가변형 Ansatz 파라미터 회로 구현 (`qaoa_circuit.py`)
  - Estimator 기반 COBYLA 하이브리드 최적화 루프 및 Sampler 계측 파이프라인 (`optimizer.py`)
- **US-05: 고전 알고리즘 벤치마크 산출**
  - 전수조사 기반 최적해 탐색 엔진 (`brute_force`)
  - Goemans-Williamson SDP 기반 다항 시간 근사 엔진 (`classical/sdp_cut.py`)
- **시스템 통합 및 인터페이스**
  - FastAPI 기반 알고리즘 3종 교차 검증 API 구축 (`main.py`)
  - Streamlit 기반 실시간 연동 대시보드 및 지표 차트 구현 (`visual/dashboard.py`)
  - 그래프 분할 및 가중치 기본 시각화 뷰어 구현 (`visual/graph_view.py`)

---

## 2. R&R (역할 분담)

| 담당자 | 포지션 | 담당 업무 및 세부 범위 |
| :--- | :--- | :--- |
| **정민주 (팀장)** | **Quantum Core & System Architecture** | • 실제 IBM QPU 백엔드 및 FakeProvider 연동 (`US-03`)<br>• Readout M3 및 ZNE(Zero-Noise Extrapolation) 오류 완화 엔진 구축 (`US-04`)<br>• 노이즈 시뮬레이터 파라미터 제어 모듈 (`US-12`)<br>• 전체 시스템 통합 및 최종 배포 파이프라인 관리 |
| **최정호** | **Backend & Data Pipeline** | • QPU 비동기 실행 상태 실시간 알림/폴링 API 구현 (`US-10`)<br>• 4자(BF, SDP, Raw QAOA, Mitigated QAOA) 벤치마크 결과 통합<br>• 결과 데이터 CSV/JSON 다운로드 스트림 API 개발 (`US-11`)<br>• 백엔드 예외 처리 및 API 스키마 유지보수 |
| **최지원** | **Frontend & Interactive Visualization** | • 웹 캔버스 기반 갈등 그래프 빌더 (노드/엣지 동적 생성·수정) (`US-06`)<br>• 파티 2분할 공간 시각화 (A/B 그룹 컬러링 및 컷 엣지 하이라이트) (`US-07`)<br>• 오류 복원 전/후 및 4자 벤치마크 대시보드 UI 연동 (`US-08`)<br>• 대표 갈등 시나리오 프리셋 UI 로더 연계 (`US-09`) |

---

## 3. Sprint 2 로드맵 (~11/19 마일스톤)

| 일자 | 마일스톤 구분 | 정민주 (Quantum Core) | 최정호 (Backend) | 최지원 (Frontend) |
| :--- | :--- | :--- | :--- | :--- |
| **11/10 (화)** | 기본 환경 설정 | IBM Quantum Runtime 연동 환경 구성 (US-03) | 비동기 Job 큐 캐시 설계 및 상태 조회 엔드포인트 규격화 (US-10) | 노드/엣지 생성용 웹 캔버스 인터랙션 프로토타입 (US-06) |
| **11/11 (수)** | 핵심 파이프라인 1 | 가상 QPU/Aer 노이즈 모델 연동 함수 구현 (US-03) | Qiskit Job 폴링 비동기 백그라운드 태스크 구현 (US-10) | 캔버스 그래프 데이터를 인접 행렬 JSON으로 파싱 (US-06) |
| **11/12 (목)** | 핵심 파이프라인 2 | M3(Matrix-free Measurement Mitigation) 판독 보정 구현 (US-04) | Job 상태 실시간 조회 API 완성 (`/jobs/{job_id}`) (US-10) | 비트스트링 결과 기반 노드 2분할 색상 하이라이트 UI (US-07) |
| **11/13 (금)** | 핵심 파이프라인 3 | ZNE(Zero-Noise Extrapolation) 에러 보정 구현 (US-04) | 4자 벤치마크 결과 취합 로직 개발 (US-08) | 컷팅된 갈등 엣지 스타일링 및 공간 분할 UI 완성 (US-07) |
| **11/14 (토)** | 데이터/프리셋 연동 | 노이즈 파라미터 제어 인터페이스 설계 (US-12) | 벤치마크 결과 CSV/JSON 다운로드 API 개발 (US-11) | 대표 갈등 시나리오 프리셋 원클릭 로더 UI 구현 (US-09) |
| **11/15 (일) 20시 중간체크** | UI-백엔드 1차 바인딩 | Raw QAOA vs Mitigated QAOA 성능 지표 검증 | 프론트-백엔드 연동 테스트 및 응답 스키마 점검 | 대시보드 내 4자 비교 차트 배치 및 렌더링 (US-08) |
| **11/16 (월)** | 시스템 통합 | E2E 전체 파이프라인 통합 테스트 | Job 상태 알림 및 다운로드 API 프론트 연결 지원 | 캔버스 입력 → 4자 비교 차트 실시간 갱신 결합 |
| **11/17 (화)** | 성능 튜닝 및 UI 고도화 | 노이즈 레벨별 오류 완화 알고리즘 튜닝 (US-12) | API 에러 핸들링 및 대용량 노드 예외 처리 | 노이즈 시뮬레이션 파라미터 조절 슬라이더 UI (US-12) |
| **11/18 (수)** | 최종 E2E 검증 | 캔버스 입력부터 다운로드까지 전 시나리오 검증 | 서버 로깅 강화 및 API 안정화 | UI 반응형 수정 및 크로스 브라우징 점검 |
| **11/19 (목) 14시까지 완성** | 최종 릴리즈 | 코드 프리징, PR 병합, 최종 시연 시나리오 확정 | 배포 빌드 검증 | 최종 대시보드 뷰 확정 |
