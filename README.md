# 자동 백업 프로그램

원본 폴더를 지정한 주기마다 `원본폴더명_YYYYMMDD_HHMMSS` 폴더로 통째로 복사하는 백업 도구입니다.
같은 동작을 여러 언어로 구현했습니다.

| 폴더 | 언어 | 형태 | 비고 |
|---|---|---|---|
| `main.py` | Python 3 + customtkinter | GUI (Windows) | 원본 버전. `backup.spec`으로 exe 빌드 |
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

## GUI 디자인 (main.py)
`design_tokens.py` 의 토큰만 사용합니다 (팔레트 · 타입 스케일 12/14/20/24/36 · 8px 간격 · 모서리 12/8). 색은 역할(role)로 참조하고, 밝은/어두운 테마를 한 쌍으로 설계했습니다.

- **다크 모드**: OS 설정을 따르며 `BACKUP_THEME=light|dark` 로 강제할 수 있습니다. 두 테마 모두 텍스트 대비 4.5:1 이상을 테스트로 검증합니다.
- **키보드**: Tab 순서가 화면 순서와 같고, 버튼은 Space/Enter로 동작하며 포커스 링은 키보드 이동 시에만 나타납니다. 드롭다운은 Tk 위젯 한계로 아직 Tab 대상이 아닙니다.
- **검증 피드백**: 오류는 문제가 있는 입력창의 테두리에 표시되고 문구는 폼 아래에 남으며, 그 입력을 고치면 사라집니다.
- **취소 가능한 백업**: 중지하면 진행 중인 복사도 중단되고 `.partial` 폴더가 정리됩니다. GUI도 CLI처럼 완료된 백업만 최종 이름을 갖습니다 (`backup_core.py`).
- **참고한 자료** (규칙만 반영, 코드·토큰은 가져오지 않음):
  [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)(접근성·상태·다크 모드 짝 설계),
  [apple-design-marketplace](https://github.com/tekgnosis-net/apple-design-marketplace)(절제·카드 가시성),
  [shadcn-ui/ui](https://github.com/shadcn-ui/ui)(검증 상태를 컨트롤에 표시, 의미 기반 토큰),
  [ant-design](https://github.com/ant-design/ant-design)(오래 걸리는 작업의 취소, 오류 문구는 입력 시 해제, 다크 모드의 과한 고대비 회피).
  이들의 색상 토큰은 채택하지 않았습니다 (Apple 보조 텍스트 `#86868B`는 흰 배경 대비 3.5:1로 AA 미달, 프로젝트 토큰과 충돌). shadcn·antd 스킬은 React/CLI 전용이라 Tk에는 적용할 수 없습니다.

## 테스트
`python -m unittest discover tests` 가 GUI 디자인 룰(토큰·대비·리터럴 금지)과 백업 엔진(취소·원자적 쓰기·정리)을, `tests/e2e.sh <바이너리>` 가 세 CLI의 공통 규격(SPEC.md)을 검증합니다 (일반 사용자 권한 기준 58개 항목, root에서는 권한 테스트 3개 제외).
GitHub Actions가 Linux · macOS · Windows에서 자동으로 실행합니다. Windows는 로컬에서 검증하지 못해 실패를 허용하는 상태입니다.

```
tests/e2e.sh /path/to/backup
```

---
개발환경: VS Code / 작성자: 이은수
