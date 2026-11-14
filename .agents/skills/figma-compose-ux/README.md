# figma-compose-ux

Figma·Code Connect → Compose 구현 → 임시 계측 → 런타임 증거 → UX 의도 검증을 연결하는 재사용 Agent Skill입니다. [SKILL.md](SKILL.md)가 진입점이며, 프로젝트별 코드 생성과 UX 해석은 에이전트가 수행하고 반복 가능한 수집·좌표 변환·검증은 독립 Python 모듈이 수행합니다.

이 폴더 전체를 다른 저장소의 `.agents/skills/figma-compose-ux/`에 복사할 수 있습니다. 해당 호스트가 지원하면 사용자 스킬 디렉터리에도 설치할 수 있습니다. Python 3.12+, Pillow가 필요하며 adb 수집 시에는 Android SDK platform-tools와 실행 중인 기기가 필요합니다. Figma MCP와 Compose 프로젝트는 실제 작업 시 연결/제공되어야 합니다.

```bash
python3 -m pip install -r .agents/skills/figma-compose-ux/requirements.txt
python3 .agents/skills/figma-compose-ux/scripts/ux.py --help
python3 .agents/skills/figma-compose-ux/scripts/ux.py demo --output-dir /tmp/compose-ux-demo
python3 -m unittest discover -s .agents/skills/figma-compose-ux/tests -v
```

데모는 네트워크·에뮬레이터 없이 계약/이미지 파이프라인을 검증합니다. 모든 입력은 **합성 fixture**이며 앱 UX의 실제 승인 결과가 아닙니다. 기본 샘플 앱은 Android View이므로 이 패키지가 실제 Compose 빌드·Figma 연동까지 검증되었다고 보지 않습니다.

| 기능 | 모듈 | 입력 → 출력 |
|---|---|---|
| 디자인·매핑 준비 | `design.py` | 의도 계약 + Compose 매핑 → 검증된 계약/이슈 |
| 런타임 관측 | `runtime.py` | adb 또는 테스트 adapter JSON → 캡처/노드/실측 insets |
| 임시 코드 수명 관리 | `instrumentation.py` | 정확한 패치/해시 → 세션 → 안전한 복원/충돌 |
| 좌표·이미지 | `imaging.py` | 원본 + insets + density → 정렬 이미지/차이 |
| 의도 검사 | `assessment.py` | 계약 + 상태별 관측 + trace → 요구사항별 판정 |
| 리포트 | `reporting.py` | 같은 판정 JSON → 근거를 포함한 Markdown |
| 도구 사용/Compose 생성 | [workflow](references/workflow.md) | 실제 MCP 응답 + 프로젝트 → 소스/빌드 증거 |

[계약·CLI](references/contracts.md), [계측·복원](references/instrumentation.md), [평가 시나리오](evals/README.md)를 참고하세요. `pass`는 선언된 항목의 관측 일치를 뜻하며 전체 UX 점수는 생성하지 않습니다. 누락 증거는 `inconclusive`입니다. 실제 화면과 행동에 대한 정성 검토를 함께 수행합니다.
