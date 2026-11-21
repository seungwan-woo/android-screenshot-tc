# Android emulator screenshot CI

실제 에뮬레이터 화면을 캡처해 PNG 기준 이미지와 비교하는 최소 샘플입니다. [Android 공식 screenshot testing 문서](https://developer.android.com/training/testing/ui-tests/screenshot)의 기준 이미지 비교 방식을 사용합니다. Compose Preview나 호스트 렌더링이 아니라 `adb exec-out screencap -p`로 전체 디스플레이를 캡처합니다.

샘플 앱은 Jetpack Compose와 Material 3로 구현한 Screenshot Lab입니다. `Update state`를 누르면 `State: READY`가 `State: UPDATED`로 바뀝니다. 시스템 라이트·다크 설정에 따라 색상과 시스템 바 아이콘이 바뀝니다. 화면 배경은 시스템 바까지 확장하고 콘텐츠에는 `WindowInsets.safeDrawing`을 적용합니다.

빌드는 JDK 21, Android SDK Platform 37.1 (`platforms;android-37.1`), Build Tools 37.0.0을 사용합니다. 샘플에 포함된 Gradle 9.9.2 Wrapper에서 AGP 9.5.2, Kotlin 2.4.21, Compose BOM 2026.11.01(Compose UI 1.13.0, Material 3 1.5.0)을 사용합니다. 실행 검증은 API 35 에뮬레이터에서 합니다.

## 실행

현재 클라우드 작업공간에서:

```bash
source /workspace/shared/android-ci/env.sh
python3 /workspace/shared/android-ci/start.py --timeout 900
cd /workspace/android-screenshot-tc
python3 -m unittest discover -s tests -v
python3 ci/android/smoke.py
bash ci/android/ci-check.sh
```

다른 개발 머신에서는 위 Android SDK 패키지, JDK 21과 Python 3.12를 설치하고 `ANDROID_HOME`/`PATH`를 설정한 후 `python3 -m pip install -r requirements.txt`를 실행하세요. API 35 default x86_64 이미지 revision 2, emulator 37.2.13(build 16740729), Pixel 2 에뮬레이터를 실행합니다. `ANDROID_SERIAL`로 테스트 기기를 선택할 수 있습니다. 클라우드에는 KVM이 없어 부팅이 느릴 수 있으며, CI는 KVM이 제공되는 Ubuntu 실행기를 사용합니다.

## 검증 내용

- CLI 테스트: 일치/차이, 픽셀 및 비율 허용치 경계, 크기 불일치, 누락·손상된 PNG, 이미지 revision 변경.
- `smoke.py`: APK 빌드·서명 검증·설치 → UI hierarchy에서 READY 확인 → 같은 화면 비교 통과 → 실제 버튼 조작 → UPDATED 확인 → 바뀐 화면 비교 실패(exit 1) 확인.
- `ci-check.sh`: 샘플 초기 화면을 저장된 기준 이미지와 비교. 차이는 exit 1, 입력 오류는 exit 2이며 CI에 그대로 전달됩니다.

화면은 1080×1920, 420 dpi, 세로 방향, font scale 1.0으로 맞춥니다. SwiftShader와 같은 이미지 revision을 사용하고 애니메이션 및 상태 표시줄의 시간·배터리·알림 표시를 고정합니다. 기본 허용치는 변경 픽셀 0개입니다. 필요할 때만 `compare.py --max-diff-ratio 0.0001 --channel-tolerance 2`처럼 허용치를 명시하세요.

## 기준 이미지 검토와 갱신

```bash
# 후보만 생성하고 기존 기준 이미지는 변경하지 않습니다.
SCREENSHOT_MODE=record bash ci/android/ci-check.sh
# 후보를 검토한 뒤 명시적으로 반영합니다.
mkdir -p ci/android/reference
cp ci/android/artifacts/ci/actual.png ci/android/reference/sample.png
# 기준 이미지와 다시 비교합니다.
SCREENSHOT_MODE=verify bash ci/android/ci-check.sh
```

라이트 기준은 `ci/android/reference/sample.png`, 다크 기준은 `ci/android/reference/sample-dark.png`에 저장합니다. 다크 기준으로 실행할 때는 `SCREENSHOT_CONFIG=ci/android/configs/sample-dark.json`을 지정합니다. 변경 시 reference/actual/diff 이미지와 `result.json`이 생성됩니다. 크기가 다르면 reference/actual과 불일치 사유를 남기고 실패합니다. PR 검증은 기준 이미지를 자동으로 덮어쓰지 않습니다. 환경·폰트·화면 크기·이미지 revision을 바꾸는 경우 기준 이미지도 별도로 검토해야 합니다.

GitHub Actions는 branch push, PR, 수동 실행을 지원하고 실패한 실행에서도 `artifacts/`를 업로드합니다. 수동 `record`는 후보만 업로드합니다. 처음 워크플로를 추가하는 PR에서는 아직 기본 브랜치에 워크플로가 없으므로 수동 실행에 의존하지 않습니다. 최초 branch push의 캡처 artifact를 검토해 baseline을 추가한 다음, 후속 push의 verify를 통과시킵니다. 샘플 기준 이미지는 제품 디자인에 대한 승인을 대신하지 않습니다.

## 실제 앱으로 바꾸기

```bash
python3 ci/android/capture.py --apk /path/to/app-debug.apk \
  --component com.example.app/.MainActivity --output artifacts/app.png
python3 ci/android/compare.py screenshots/reference.png artifacts/app.png \
  --artifacts artifacts/comparison
```

`--no-launch`는 화면 설정·상태 표시줄·앱을 변경하지 않고 현재 화면을 캡처합니다. 첫 캡처에서 환경을 준비한 뒤 화면 조작과 후속 캡처에 사용하세요. 실제 앱에서는 Espresso/UI Automator 등으로 테스트 상태까지 이동하고 데이터·시간·네트워크 응답을 고정한 뒤 캡처하세요. APK 빌드 출력·debug keystore·SDK·에뮬레이터 데이터는 Git에 넣지 않습니다.

## Figma·Compose UX 의도 검증 스킬

[figma-compose-ux](.agents/skills/figma-compose-ux/README.md)는 Figma MCP·Code Connect 정보를 바탕으로 Compose를 구현하고, 임시 testTag/insets 계측과 스크린샷·UI Automator·Semantics 증거를 연결하는 재사용 스킬입니다. 기능별 CLI와 공통 JSON 계약, 안전한 임시 코드 복원, 요구사항별 판정 및 리포트를 제공합니다.

```bash
python3 .agents/skills/figma-compose-ux/scripts/ux.py demo --output-dir /tmp/compose-ux-demo
python3 -m unittest discover -s .agents/skills/figma-compose-ux/tests -v
```

이 데모와 별도 `Compose UX skill` CI는 합성 데이터로 도구 동작을 검증합니다. 기존 실제 에뮬레이터 screenshot CI와 구분됩니다. 실제 Figma·Compose 프로젝트에 적용할 때는 해당 MCP 연결, 앱 빌드 및 상태별 런타임 관측이 필요합니다.

## 설정 파일로 Actions 실행하고 결과 보관하기

GitHub의 **Actions → Emulator screenshot test → Run workflow**에서 저장소 기준 `config` 경로와 `mode`를 지정합니다. [기본 설정](ci/android/configs/sample.json)은 Compose 샘플을 라이트 테마로 빌드·실행하고 화면 전체를 비교합니다. 다크 버전은 [다크 설정](ci/android/configs/sample-dark.json)을 선택합니다. Push와 PR에서는 두 설정을 별도 에뮬레이터에서 검사합니다.

```bash
gh workflow run screenshot.yml --ref main \
  -f config=ci/android/configs/sample.json -f mode=verify -f publish_pages=false
```

Compose 앱을 같은 저장소에서 실행할 때는 앱의 실제 경로와 컴포넌트, 기준 PNG를 가진 설정 파일을 추가합니다. 다음은 특정 패널을 비교하는 예시입니다.

```json
{
  "schema_version": 1,
  "name": "Compose button panel",
  "gradle": {"directory": "examples/compose-app", "task": ":app:assembleDebug"},
  "apk": "examples/compose-app/app/build/outputs/apk/debug/app-debug.apk",
  "component": "com.example.app/.MainActivity",
  "reference": "screenshots/buttons.png",
  "size": "480x800",
  "density": 160,
  "theme": "dark",
  "crop": [47, 108, 433, 384],
  "settle_seconds": 3,
  "focus_timeout": 25,
  "channel_tolerance": 0,
  "max_diff_ratio": 0,
  "smoke": false
}
```

- `gradle`을 지정하면 해당 디렉터리의 Wrapper로 APK를 빌드합니다. 이미 준비된 APK를 사용할 때는 `gradle`을 생략합니다. 둘 다 생략하면 기본 샘플을 빌드합니다.
- `crop`은 실제 디스플레이 좌표의 `[left, top, right, bottom]`이며 선택 사항입니다. 예시의 기준 PNG는 `386×276`이어야 하며 이미지 크기를 강제로 맞추지 않습니다. 앱과 기준 이미지에 맞는 값을 사용하세요.
- `verify`는 기준 PNG와 비교합니다. `record`는 후보 이미지를 남깁니다. 프로젝트에서 필요한 SDK·빌드 의존성은 앱 빌드 단계에 맞춰 준비하세요.
- `theme`에 `light`, `dark`, `system`을 지정할 수 있습니다. `smoke: true`는 내장 Compose 샘플의 기본 화면 설정에서 테마 전환과 버튼 상태를 확인합니다. 실제 앱의 상태 전이는 앱에 맞는 계측 테스트에서 실행하세요.

모든 실행은 Actions 아티팩트에 `report/index.html`과 JSON, 비교 이미지 및 캡처 진단을 남깁니다. 캡처 전후 전면 앱을 확인하므로 런처 응답 없음이 끼어들면 환경 오류로 기록됩니다. CI는 Quickstep 응답 없음이 확인된 경우 전용 에뮬레이터에서 런처를 한 차례 재시작합니다.

GitHub Pages는 저장소 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 한 번 설정한 뒤 사용합니다. `main`의 수동 실행에서 `publish_pages: true`를 선택하면 `gh-pages` 브랜치에 `runs/<run-id>-<attempt>/`가 추가되고, 인덱스가 갱신됩니다. 실패한 비교도 보관되며, 동일 실행을 다시 시도하면 별도 항목이 됩니다. Pages에 공개할 수 있는 이미지와 진단만 있는 실행에서 켜세요. 이전 보고서와 인덱스는 브랜치에 보관되므로 Actions 아티팩트 만료와 관계없이 조회할 수 있습니다.
