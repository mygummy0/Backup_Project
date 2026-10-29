# 자동 백업 프로그램

원본 폴더를 지정한 주기마다 `원본폴더명_YYYYMMDD_HHMMSS` 폴더로 통째로 복사하는 백업 도구입니다.
같은 동작을 여러 언어로 구현했습니다.

| 폴더 | 언어 | 형태 | 비고 |
|---|---|---|---|
| `main.py` | Python 3 + customtkinter | GUI (Windows) | 원본 버전. `backup.spec`으로 exe 빌드 |
| `go/` | Go 1.21+ | CLI | 표준 라이브러리만 사용 |
| `rust/` | Rust 2021 | CLI | `chrono`, `ctrlc` |
| `cpp/` | C++17 | CLI | CMake, 외부 의존성 없음 |

## CLI 사용법 (Go / Rust / C++ 공통)

```
backup --source <원본> --target <저장폴더> [--interval 5m] [--keep N] [--once] [--log-file <파일>]
```

| 옵션 | 설명 |
|---|---|
| `--source`, `--target` | 필수. 둘 다 존재하는 폴더여야 합니다 |
| `--interval` | `30s`, `5m`, `1h` 형식. 기본 `5m` |
| `--keep N` | 최근 N개만 보관하고 오래된 백업 삭제. 기본 `0`(무제한) |
| `--once` | 한 번만 백업하고 종료 |
| `--log-file` | 로그를 파일에도 추가 저장 |

실행 중 `Ctrl+C`로 중지합니다.

## 빌드

```
cd go   && go build -o backup .
cd rust && cargo build --release        # rust/target/release/backup
cd cpp  && cmake -S . -B build && cmake --build build   # cpp/build/backup
```

## 안전장치 (모든 버전 공통)
- 저장 폴더가 원본 폴더 안에 있거나 같으면 거부합니다 (무한 복사 방지).
- 백업이 순차 실행되어 겹치지 않습니다 (Python은 이전 백업이 진행 중이면 건너뜀).
- 이미 존재하는 백업 파일은 덮어쓰지 않습니다.
- 심볼릭 링크는 따라가지 않고 건너뛰며 로그에 개수를 남깁니다.
- `--keep`은 `원본명_YYYYMMDD_HHMMSS` 형식의 폴더만 지우고 다른 폴더는 건드리지 않습니다.

## 테스트
`tests/e2e.sh <바이너리>` 가 세 CLI의 공통 규격(15개 항목)을 검증합니다. GitHub Actions에서도 자동 실행됩니다.

```
tests/e2e.sh /path/to/backup
```

---
개발환경: VS Code / 작성자: 이은수
