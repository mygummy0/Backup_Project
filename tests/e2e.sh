#!/usr/bin/env bash
# Usage: tests/e2e.sh <path-to-backup-binary>
# Verifies the shared CLI contract in SPEC.md; run against the Go, Rust and C++ builds.
set -u
BIN="$1"
T=$(mktemp -d); trap 'chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"' EXIT
fail=0
WIN=0; case "${OSTYPE:-}" in msys*|cygwin*|win32*) WIN=1;; esac
check() { if [ "$2" = "0" ]; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }
skip()  { echo "SKIP $1"; }
rc_is() { [ "$1" = "$2" ]; }
run()   { "$BIN" "$@"; }     # stdout+stderr are captured by the caller
count() { ls -1 "$1" 2>/dev/null | grep -c "$2"; }

mkdir -p "$T/src/sub" "$T/dst"
echo hello > "$T/src/a.txt"; echo world > "$T/src/sub/b.txt"
[ $WIN = 0 ] && ln -s a.txt "$T/src/link"

# ---- 1. basic backup --------------------------------------------------------
run --source "$T/src" --target "$T/dst" --once > "$T/out1" 2>&1; rc=$?
check "once exits 0" $(rc_is $rc 0; echo $?)
B=$(ls "$T/dst" | head -1)
[[ "$B" =~ ^src_[0-9]{8}_[0-9]{6}$ ]]; check "folder name src_YYYYMMDD_HHMMSS" $?
[ "$(cat "$T/dst/$B/sub/b.txt" 2>/dev/null)" = "world" ]; check "nested file copied" $?
[ -e "$T/dst/$B/link" ] && r=1 || r=0; [ $WIN = 1 ] && r=0; check "symlink not followed/copied" $r
grep -q "✅ 백업 완료" "$T/out1"; check "success log" $?
grep -q "폴더 용량" "$T/out1"; check "size in log" $?
grep -q "📦 복사 2개, 재사용 0개, 제외 0개" "$T/out1"; check "summary line (2 copied)" $?
[ "$(count "$T/dst" '\.partial$')" = "0" ]; check "no .partial left after success" $?
grep -qE '^\[[0-9]{2}:[0-9]{2}:[0-9]{2}\] ' "$T/out1"; check "log lines have [HH:MM:SS] prefix" $?

# ---- 2. mtime preserved -----------------------------------------------------
touch -t 202001020304 "$T/src/a.txt"
sleep 1.1
run --source "$T/src" --target "$T/dst" --once >/dev/null 2>&1
B2=$(ls "$T/dst" | sort | tail -1)
[ ! "$T/src/a.txt" -nt "$T/dst/$B2/a.txt" ] && [ ! "$T/src/a.txt" -ot "$T/dst/$B2/a.txt" ]; check "mtime preserved" $?

# ---- 3. exit codes / validation --------------------------------------------
mkdir -p "$T/src/inner"
run --source "$T/src" --target "$T/src/inner" --once >/dev/null 2>&1; rc_is $? 1; check "target inside source -> exit 1" $?
run --source "$T/src" --target "$T/src" --once >/dev/null 2>&1;       rc_is $? 1; check "target == source -> exit 1" $?
rmdir "$T/src/inner"
run --source "$T/nope" --target "$T/dst" --once >/dev/null 2>&1;      rc_is $? 1; check "missing source -> exit 1" $?
run --source "$T/src" --target "$T/nope" --once >/dev/null 2>&1;      rc_is $? 1; check "missing target -> exit 1" $?
run --source "$T/src" --target "$T/dst" --interval abc >/dev/null 2>&1; rc_is $? 2; check "bad interval -> exit 2" $?
run --source "$T/src" --target "$T/dst" --interval 0s  >/dev/null 2>&1; rc_is $? 2; check "zero interval -> exit 2" $?
run --source "$T/src" --target "$T/dst" --mode bogus --once >/dev/null 2>&1; rc_is $? 2; check "bad mode -> exit 2" $?
run --source "$T/src" >/dev/null 2>&1;                                rc_is $? 2; check "missing --target -> exit 2" $?
run --source "$T/src" --target "$T/dst" --bogus >/dev/null 2>&1;      rc_is $? 2; check "unknown flag -> exit 2" $?
run --source "$T/src" --target "$T/dst" --keep -1 --once >/dev/null 2>&1; rc_is $? 2; check "negative keep -> exit 2" $?

# ---- 4. retention + .partial handling --------------------------------------
rm -rf "$T/dst"; mkdir "$T/dst"
for d in 20240101_000001 20240101_000002 20240101_000003; do mkdir "$T/dst/src_$d"; done
mkdir "$T/dst/other_20240101_000001" "$T/dst/src_20240101_000009.partial"
run --source "$T/src" --target "$T/dst" --once --keep 2 >"$T/out4" 2>&1
[ "$(count "$T/dst" '^src_[0-9]\{8\}_[0-9]\{6\}$')" = "2" ]; check "keep=2 prunes to 2" $?
[ -d "$T/dst/other_20240101_000001" ]; check "other prefixes untouched" $?
[ ! -d "$T/dst/src_20240101_000001" ] && [ ! -d "$T/dst/src_20240101_000002" ]; check "oldest removed" $?
[ -d "$T/dst/src_20240101_000009.partial" ]; check "foreign .partial ignored by prune" $?
grep -q "🗑 오래된 백업 삭제: src_20240101_000001" "$T/out4"; check "prune log line" $?

# ---- 5. log file ------------------------------------------------------------
sleep 1.1
run --source "$T/src" --target "$T/dst" --once --log-file "$T/log.txt" >/dev/null 2>&1
grep -q "백업 완료" "$T/log.txt"; check "log file written" $?

# ---- 6. exclude globs -------------------------------------------------------
X="$T/x"; mkdir -p "$X/sub" "$X/node_modules/pkg" "$X/build/out" "$X/build/keep" "$X/docs/a/b"
echo 1 > "$X/a.log"; echo 1 > "$X/sub/b.log"; echo 1 > "$X/sub/keep.txt"; echo 1 > "$X/sub/other.txt"
echo 1 > "$X/node_modules/pkg/x.js"; echo 1 > "$X/build/out/o.bin"; echo 1 > "$X/build/keep/k.bin"
echo 1 > "$X/docs/a/b/c.md"; echo 1 > "$X/docs/a/d.md"; echo 1 > "$X/file1.tmp"; echo 1 > "$X/file12.tmp"; echo 1 > "$X/main.rs"
rm -rf "$T/dst"; mkdir "$T/dst"
run --source "$X" --target "$T/dst" --once \
    --exclude '*.log' --exclude node_modules --exclude build/out --exclude 'docs/**/c.md' \
    --exclude 'sub/*.txt' --exclude 'file?.tmp' >"$T/out6" 2>&1; rc=$?
check "exclude run exits 0" $(rc_is $rc 0; echo $?)
D="$T/dst/$(ls "$T/dst" | head -1)"
[ ! -e "$D/a.log" ] && [ ! -e "$D/sub/b.log" ]; check "*.log excluded at any depth" $?
[ ! -e "$D/node_modules" ]; check "excluded directory skipped entirely" $?
[ ! -e "$D/build/out" ] && [ -e "$D/build/keep/k.bin" ]; check "path pattern build/out only" $?
[ ! -e "$D/docs/a/b/c.md" ] && [ -e "$D/docs/a/d.md" ]; check "** matches nested dirs" $?
[ ! -e "$D/sub/keep.txt" ] && [ ! -e "$D/sub/other.txt" ]; check "sub/*.txt matches path" $?
[ ! -e "$D/file1.tmp" ] && [ -e "$D/file12.tmp" ]; check "? matches exactly one char" $?
[ -e "$D/main.rs" ]; check "unmatched file kept" $?
grep -qE "📦 복사 [0-9]+개, 재사용 0개, 제외 [1-9][0-9]*개" "$T/out6"; check "exclude count in summary" $?

# ---- 7. incremental (hardlink snapshots) -----------------------------------
I="$T/inc"; mkdir -p "$I/sub"; echo "aaaa" > "$I/a.txt"; echo "bbbb" > "$I/sub/b.txt"
rm -rf "$T/dst"; mkdir "$T/dst"
run --source "$I" --target "$T/dst" --once --mode incremental >"$T/o1" 2>&1
grep -q "📦 복사 2개, 재사용 0개" "$T/o1"; check "incremental #1 copies everything" $?
sleep 1.1
run --source "$I" --target "$T/dst" --once --mode incremental >"$T/o2" 2>&1
grep -q "📦 복사 0개, 재사용 2개" "$T/o2"; check "incremental #2 reuses all" $?
S1=$(ls "$T/dst" | sort | sed -n 1p); S2=$(ls "$T/dst" | sort | sed -n 2p)
[ "$(cat "$T/dst/$S2/sub/b.txt")" = "bbbb" ]; check "reused file has content" $?
if [ $WIN = 0 ]; then [ "$T/dst/$S1/a.txt" -ef "$T/dst/$S2/a.txt" ]; check "unchanged file is hardlinked" $?
else skip "hardlink identity (windows)"; fi
echo "changed-and-longer" > "$I/a.txt"
sleep 1.1
run --source "$I" --target "$T/dst" --once --mode incremental >"$T/o3" 2>&1
grep -q "📦 복사 1개, 재사용 1개" "$T/o3"; check "incremental #3 copies only changed" $?
S3=$(ls "$T/dst" | sort | sed -n 3p)
[ "$(cat "$T/dst/$S3/a.txt")" = "changed-and-longer" ] && [ "$(cat "$T/dst/$S2/a.txt")" = "aaaa" ]; check "old snapshot keeps old content" $?
if [ $WIN = 0 ]; then [ ! "$T/dst/$S2/a.txt" -ef "$T/dst/$S3/a.txt" ] && [ "$T/dst/$S2/sub/b.txt" -ef "$T/dst/$S3/sub/b.txt" ]; check "changed not linked, unchanged linked" $?
else skip "hardlink identity (windows)"; fi
sleep 1.1
run --source "$I" --target "$T/dst" --once --mode full >"$T/o4" 2>&1
grep -q "📦 복사 2개, 재사용 0개" "$T/o4"; check "full mode never reuses" $?

# ---- 8. verify --------------------------------------------------------------
rm -rf "$T/dst"; mkdir "$T/dst"
run --source "$I" --target "$T/dst" --once --verify >"$T/o5" 2>&1; rc=$?
check "verify exits 0" $(rc_is $rc 0; echo $?)
grep -q "🔍 검증 완료: 2개 파일 일치" "$T/o5"; check "verify log" $?

# ---- 9. dry-run -------------------------------------------------------------
rm -rf "$T/dst"; mkdir "$T/dst"
run --source "$I" --target "$T/dst" --dry-run --exclude '*.zzz' >"$T/o6" 2>&1; rc=$?
check "dry-run exits 0" $(rc_is $rc 0; echo $?)
[ -z "$(ls -A "$T/dst")" ]; check "dry-run writes nothing" $?
grep -q "🧪 \[dry-run\]" "$T/o6" && grep -q "📦 복사 2개" "$T/o6"; check "dry-run reports plan" $?

# ---- 10. unicode / spaces ---------------------------------------------------
U="$T/내 원본 폴더"; mkdir -p "$U/하위 폴더"; echo ok > "$U/하위 폴더/파일 이름.txt"
rm -rf "$T/dst"; mkdir "$T/dst"
run --source "$U" --target "$T/dst" --once --keep 5 --exclude '파일?이름.zip' >"$T/o7" 2>&1; rc=$?
check "unicode source exits 0" $(rc_is $rc 0; echo $?)
[ "$(cat "$T/dst/"내\ 원본\ 폴더_*/하위\ 폴더/파일\ 이름.txt 2>/dev/null)" = "ok" ]; check "unicode names copied" $?
echo x > "$U/파일가이름.txt"; sleep 1.1
run --source "$U" --target "$T/dst" --once --exclude '파일?이름.txt' >/dev/null 2>&1
LAST=$(ls -d "$T/dst/"* | sort | tail -1)
[ ! -e "$LAST/파일가이름.txt" ]; check "? matches one unicode char" $?

# ---- 11. failure leaves no partial backup (needs a non-root user) ----------
if [ "$(id -u)" != "0" ] && [ $WIN = 0 ]; then
  F="$T/fail"; mkdir -p "$F/locked"; echo 1 > "$F/ok.txt"; echo 1 > "$F/locked/s.txt"; chmod 000 "$F/locked"
  rm -rf "$T/dst"; mkdir "$T/dst"
  run --source "$F" --target "$T/dst" --once >"$T/o8" 2>&1; rc=$?
  chmod 755 "$F/locked"
  rc_is $rc 1; check "unreadable dir -> exit 1" $?
  grep -q "❌ 오류 발생" "$T/o8"; check "error logged" $?
  [ -z "$(ls -A "$T/dst")" ]; check "failed backup leaves nothing behind" $?
else skip "failure cleanup (needs non-root, non-windows)"; fi

# ---- 12. loop mode ----------------------------------------------------------
if [ $WIN = 0 ]; then
  rm -rf "$T/dst"; mkdir "$T/dst"
  "$BIN" --source "$T/src" --target "$T/dst" --interval 1s > "$T/loop" 2>&1 &
  P=$!; sleep 3.5; kill -INT $P; wait $P; rc=$?
  n=$(ls "$T/dst" | wc -l); [ "$n" -ge 2 ]; check "loop made >=2 backups (got $n)" $?
  grep -q "자동 백업 시작됨 (주기: 1s)" "$T/loop"; check "loop start message" $?
  grep -q "중지" "$T/loop"; check "stop message on SIGINT" $?
  rc_is $rc 0; check "SIGINT exits 0 (got $rc)" $?
else skip "loop/SIGINT (windows)"; fi

exit $fail
