# 자동 백업 프로그램

원본 폴더를 지정한 주기마다 `원본폴더명_YYYYMMDD_HHMMSS` 폴더로 통째로 복사하는 백업 도구입니다.
같은 동작을 여러 언어로 구현했습니다.

| 폴더 | 언어 | 형태 | 비고 |
|---|---|---|---|
| `gui-tauri/` | Tauri 2 + React + shadcn/ui | GUI | Rust 엔진 사용 (권장) |
| `main.py` | Python 3 + customtkinter | GUI (Windows) | 레거시. `backup.spec`으로 exe 빌드 |
| `go/` | Go 1.21+ | CLI | 표준 라이브러리만 사용 |
| `rust/` | Rust 2021 | CLI | `chrono`, `ctrlc` |
| `cpp/` | C++17 | CLI | CMake, 외부 의존성 없음 |

## CLI 사용법 (Go / Rust / C++ 공통, 명세: [SPEC.md](SPEC.md))

```
backup --source <원본> --target <저장폴더> [--interval 5m] [--keep N] [--once]
       [--mode full|incremental] [--exclude <글롭>]... [--verify] [--dry-run] [--log-file <파일>]
```

| 옵션 | 설명 |
|---|---|
| `--source`, `--target` | 필수. 둘 다 존재하는 폴더여야 합니다 |
| `--interval` | `30s`, `5m`, `1h` 형식. 기본 `5m` |
| `--keep N` | 최근 N개만 보관하고 오래된 백업 삭제. 기본 `0`(무제한) |
| `--mode incremental` | 변경 없는 파일(크기·수정시각 동일)은 직전 백업에 **하드링크** — 매번 완전한 스냅샷이면서 디스크는 변경분만 사용 |
| `--exclude` | 제외 글롭, 여러 번 지정 가능. `*.log`, `node_modules`, `build/out`, `docs/**/c.md`, `file?.tmp` |
| `--verify` | 복사한 파일을 원본과 바이트 비교 |
| `--dry-run` | 아무것도 쓰지 않고 복사/재사용/제외 개수만 출력 |
| `--once` | 한 번만 백업하고 종료 |
| `--log-file` | 로그를 파일에도 추가 저장 |

종료 코드: `0` 성공 · `1` 백업/경로 검증 실패 · `2` 사용법 오류. 반복 모드는 `Ctrl+C`(SIGINT)·SIGTERM으로 중지합니다.

## 빌드

```
cd go   && go build -o backup .
cd rust && cargo build --release        # rust/target/release/backup
cd cpp  && cmake -S . -B build && cmake --build build   # cpp/build/backup
```

## 안전장치 (모든 CLI 공통)
- 저장 폴더가 원본 폴더 안에 있거나 같으면 거부합니다 (무한 복사 방지).
- `원본_날짜.partial` 에 복사한 뒤 완료되면 이름을 바꿉니다. 도중에 실패해도 반쪽짜리 백업이 남지 않고, 정리·증분 대상에서도 제외됩니다.
- 백업이 순차 실행되어 겹치지 않으며, 같은 이름의 백업이 있으면 덮어쓰지 않고 오류로 처리합니다.
- 심볼릭 링크는 따라가지 않고 건너뛰며 개수를 로그에 남깁니다.
- 파일 수정 시각을 보존합니다.
- `--keep`은 `원본명_YYYYMMDD_HHMMSS` 형식의 폴더만 지우고 다른 폴더는 건드리지 않습니다.
- 로그의 "폴더 용량"은 하드링크를 각각 합산한 겉보기 크기라, 증분 모드의 실제 디스크 사용량보다 큽니다.

## GUI (Tauri · `gui-tauri/`)
Rust 엔진(`rust/`, `backup` 크레이트)을 그대로 쓰는 데스크톱 앱입니다. React + Tailwind v4 + shadcn/ui.

```
cd gui-tauri
npm install
npm run tauri dev                  # 개발 실행 (Tauri + Vite)
npx tauri build --no-bundle        # 릴리스 바이너리: src-tauri/target/release/backup-gui
npm run build && npx vite preview --port 4173   # 브라우저 미리보기(목 백엔드)
node scripts/shots.mjs <출력폴더>   # 상태 6종 x 라이트/다크 캡처 + 접근성·상태 검증 28항목
```
- **화면**: 상단에 설정 버튼(톱니), 원본·저장 폴더, 타이머와 시작/중지, 작업 기록. 설정 창에 `일반`(주기·보관)과 `고급 옵션`(증분·검증·제외) 탭이 있습니다.
- **디자인**: JetBrains Mono(숫자·경로) + Pretendard(한글, 글리프 대체), 딥 네이비/흑백 기반, 그림자 없이 얇은 테두리, 전환 300ms, 폰트 굵기 300/400/600. 이모지·그라디언트·인디고 강조색을 쓰지 않습니다.
- **키보드**: Tab 순서 = 화면 순서. 포커스 표시는 키보드로 이동할 때만 2px 외곽선(마우스 클릭에는 나타나지 않음).
- **수정하는 곳**: 색·간격·모션 `design_tokens.py`(→ `python gui-tauri/scripts/gen_tokens.py`), 문구 `src/lib/copy.ts`, 화면 배치 `src/App.tsx`, 설정 창 `src/components/SettingsDialog.tsx`, 백엔드 명령 `src-tauri/src/lib.rs`, 창 크기·아이콘 `src-tauri/tauri.conf.json`.
- **지켜지는 규칙**: `tests/test_gui_design_guard.py` 가 간격·글자 크기·모서리·원색 클래스·굵기·그림자·그라디언트·전환 시간·이모지·폰트를 정적으로 검사합니다.

## 레거시 GUI (Tk, `main.py`)
같은 `design_tokens.py` 를 쓰므로 색·전환이 함께 바뀝니다. 다크 모드는 OS 설정을 따르며 `BACKUP_THEME=light|dark` 로 강제할 수 있습니다.
- 오류는 문제가 있는 입력창의 테두리에 표시되고, 그 입력을 고치면 사라집니다.
- 중지하면 진행 중인 복사도 중단되고 `.partial` 폴더가 정리됩니다 (`backup_core.py`).
- 참고한 자료(규칙만 반영, 코드·토큰은 가져오지 않음): [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), [apple-design-marketplace](https://github.com/tekgnosis-net/apple-design-marketplace), [shadcn-ui/ui](https://github.com/shadcn-ui/ui), [ant-design](https://github.com/ant-design/ant-design). 이들의 색상 토큰은 채택하지 않았습니다.

## 테스트
`python -m unittest discover tests` 가 GUI 디자인 룰(토큰·대비·리터럴 금지)과 백업 엔진(취소·원자적 쓰기·정리)을, `tests/e2e.sh <바이너리>` 가 세 CLI의 공통 규격(SPEC.md)을 검증합니다 (일반 사용자 권한 기준 58개 항목, root에서는 권한 테스트 3개 제외).
GitHub Actions가 Linux · macOS · Windows에서 자동으로 실행합니다. Windows는 로컬에서 검증하지 못해 실패를 허용하는 상태입니다.

```
tests/e2e.sh /path/to/backup
```

---
개발환경: VS Code / 작성자: 이은수
