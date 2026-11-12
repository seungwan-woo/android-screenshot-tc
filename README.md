# Android emulator screenshot CI

실제 에뮬레이터 화면을 캡처해 PNG 기준 이미지와 비교하는 최소 샘플입니다. [Android 공식 screenshot testing 문서](https://developer.android.com/training/testing/ui-tests/screenshot)의 기준 이미지 비교 방식을 사용합니다. Compose Preview나 호스트 렌더링이 아니라 `adb exec-out screencap -p`로 전체 디스플레이를 캡처합니다.

샘플 APK는 네트워크나 AndroidX 의존성 없이 Android View로 화면을 구성합니다. `Update state` 버튼을 누르면 `State: READY`가 `State: UPDATED`로 바뀝니다. 빌드에는 JDK 21, Android SDK platform 35, Build Tools 35.0.0을 사용합니다. Gradle은 필요하지 않습니다.

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

다른 개발 머신에서는 Android SDK, JDK 21과 Python 3.12를 설치하고 `ANDROID_HOME`/`PATH`를 설정한 후 `python3 -m pip install -r requirements.txt`를 실행하세요. API 35 default x86_64 이미지 revision 2, emulator 37.2.13(build 16740729), Pixel 2 에뮬레이터를 실행합니다. `ANDROID_SERIAL`로 테스트 기기를 선택할 수 있습니다. 클라우드에는 KVM이 없어 부팅이 느릴 수 있으며, CI는 KVM이 제공되는 Ubuntu 실행기를 사용합니다.

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

기준 이미지는 `ci/android/reference/sample.png`에 저장합니다. 변경 시 reference/actual/diff 이미지와 `result.json`이 생성됩니다. 크기가 다르면 reference/actual과 불일치 사유를 남기고 실패합니다. PR 검증은 기준 이미지를 자동으로 덮어쓰지 않습니다. 환경·폰트·화면 크기·이미지 revision을 바꾸는 경우 기준 이미지도 별도로 검토해야 합니다.

GitHub Actions는 branch push, PR, 수동 실행을 지원하고 실패한 실행에서도 `artifacts/`를 업로드합니다. 수동 `record`는 후보만 업로드합니다. 처음 워크플로를 추가하는 PR에서는 아직 기본 브랜치에 워크플로가 없으므로 수동 실행에 의존하지 않습니다. 최초 branch push의 캡처 artifact를 검토해 baseline을 추가한 다음, 후속 push의 verify를 통과시킵니다. 샘플 기준 이미지는 제품 디자인에 대한 승인을 대신하지 않습니다.

## 실제 앱으로 바꾸기

```bash
python3 ci/android/capture.py --apk /path/to/app-debug.apk \
  --component com.example.app/.MainActivity --output artifacts/app.png
python3 ci/android/compare.py screenshots/reference.png artifacts/app.png \
  --artifacts artifacts/comparison
```

`--no-launch`는 현재 화면을 그대로 캡처합니다. 실제 앱에서는 Espresso/UI Automator 등으로 테스트 상태까지 이동하고 데이터·시간·네트워크 응답을 고정한 뒤 캡처하세요. APK 빌드 출력·debug keystore·SDK·에뮬레이터 데이터는 Git에 넣지 않습니다.
