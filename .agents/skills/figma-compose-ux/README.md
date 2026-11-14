# figma-compose-ux

Figma·Code Connect → Compose 구현 → 임시 계측 → 런타임 증거 → UX 의도 검증을 연결하는 재사용 Agent Skill입니다. [SKILL.md](SKILL.md)가 진입점이며, 프로젝트별 코드 생성과 UX 해석은 에이전트가 수행하고 반복 가능한 수집·좌표 변환·검증은 독립 Python 모듈이 수행합니다.

이 폴더 전체를 다른 저장소의 `.agents/skills/figma-compose-ux/`에 복사할 수 있습니다. 해당 호스트가 지원하면 사용자 스킬 디렉터리에도 설치할 수 있습니다. Python 3.12+, Pillow가 필요하며 adb 수집 시에는 Android SDK platform-tools와 실행 중인 기기가 필요합니다. Figma MCP와 Compose 프로젝트는 실제 작업 시 연결/제공되어야 합니다.

## Codex·Gemini CLI·Claude Code에서 사용

Agent Skills 형식의 `SKILL.md`와 같은 Python 스크립트를 사용합니다. 실제 앱 프로젝트에서 사용할 때는 폴더 전체를 해당 프로젝트의 아래 경로에 배치하세요. PR이 머지되기 전에는 `feat/figma-compose-ux-skill` 브랜치를 사용합니다.

| 클라이언트 | 프로젝트 내 설치 경로 | 호출·확인 방법 |
|---|---|---|
| Codex | `.agents/skills/figma-compose-ux/` | `$figma-compose-ux`를 지정해 요청 |
| [Gemini CLI](https://geminicli.com/docs/cli/skills/) | `.agents/skills/figma-compose-ux/` 또는 `.gemini/skills/figma-compose-ux/` | `/skills list`로 확인하고 스킬 이름을 언급해 요청 |
| [Claude Code](https://code.claude.com/docs/en/skills) | `.claude/skills/figma-compose-ux/` | `/figma-compose-ux`로 호출 |

Gemini CLI는 현재 `.agents/skills/` 경로도 지원합니다. Claude Code에서 같은 저장소를 사용할 때의 최초 설치 예시:

```bash
mkdir -p .claude/skills
cp -R .agents/skills/figma-compose-ux .claude/skills/
```

다음처럼 요청할 수 있습니다.

> figma-compose-ux 스킬로 이 Figma URL의 화면을 Compose로 구현하고, 스크린샷과 런타임 증거로 요구사항을 검증해줘. 검증 후 임시 계측 코드는 복원해줘.

클라이언트는 프로젝트 파일·명령 실행과 MCP 도구를 사용할 수 있어야 합니다. Gemini CLI·Claude Code는 공식 문서에서 스킬 형식과 설치 경로를 확인했으며, 해당 클라이언트에서 전체 파이프라인을 실행한 검증은 아직 없습니다.

## Figma MCP 연결

스킬 설치와 MCP 인증은 각 클라이언트에서 별도로 진행합니다. 공식 원격 서버는 `https://mcp.figma.com/mcp`입니다. 로컬 Codex CLI의 등록·로그인 절차:

```bash
codex mcp add figma --url https://mcp.figma.com/mcp
codex mcp login figma
```

다른 클라이언트는 [Figma MCP 공식 가이드](https://github.com/figma/mcp-server-guide)에 따라 연결하고, 실제 세션에 Figma 도구가 표시되는지 확인하세요. 로컬 CLI에 저장한 연결은 별도 클라우드 채팅에 자동으로 전달되지 않습니다.

실제 검증에는 접근 가능한 Figma 파일·컴포넌트 URL, 디자인 조회 권한, Compose 프로젝트와 매핑 정보가 필요합니다. Code Connect 매핑 생성·게시는 별도 작업이며 MCP 연결만으로 게시가 완료되지는 않습니다. 설정 디렉터리가 읽기 전용이거나 프록시에서 Figma 도메인을 차단하면 쓰기와 네트워크 접근이 가능한 실행 환경에서 연결해야 합니다. 자세한 증거·인증 구분은 [워크플로](references/workflow.md)를 참고하세요.

## 실행과 검증 범위

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
