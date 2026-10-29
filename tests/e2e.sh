#!/usr/bin/env bash
# Usage: tests/e2e.sh <path-to-backup-binary>
# Verifies the shared CLI contract; run against the Go, Rust and C++ builds.
set -u
BIN="$1"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
check() { if [ "$2" = "0" ]; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }

mkdir -p "$T/src/sub" "$T/dst"
echo hello > "$T/src/a.txt"; echo world > "$T/src/sub/b.txt"; ln -s a.txt "$T/src/link"

# 1. single backup copies the tree
"$BIN" --source "$T/src" --target "$T/dst" --once > "$T/out1" 2>&1; rc=$?
check "once exits 0" $rc
B=$(ls "$T/dst" | head -1)
[[ "$B" =~ ^src_[0-9]{8}_[0-9]{6}$ ]]; check "folder name src_YYYYMMDD_HHMMSS" $?
[ "$(cat "$T/dst/$B/sub/b.txt" 2>/dev/null)" = "world" ]; check "nested file copied" $?
grep -q "✅ 백업 완료" "$T/out1"; check "success log" $?
grep -q "폴더 용량" "$T/out1"; check "size in log" $?

# 2. target inside source is rejected
mkdir -p "$T/src/inner"
"$BIN" --source "$T/src" --target "$T/src/inner" --once >/dev/null 2>&1; check "target inside source rejected" $([ $? -ne 0 ]; echo $?)
"$BIN" --source "$T/src" --target "$T/src" --once >/dev/null 2>&1; check "target == source rejected" $([ $? -ne 0 ]; echo $?)
rmdir "$T/src/inner"

# 3. missing dirs rejected
"$BIN" --source "$T/nope" --target "$T/dst" --once >/dev/null 2>&1; check "missing source rejected" $([ $? -ne 0 ]; echo $?)

# 4. retention keeps newest N
rm -rf "$T/dst"; mkdir "$T/dst"
for d in 20240101_000001 20240101_000002 20240101_000003; do mkdir "$T/dst/src_$d"; done
mkdir "$T/dst/other_20240101_000001"
"$BIN" --source "$T/src" --target "$T/dst" --once --keep 2 >/dev/null 2>&1
[ "$(ls -d "$T"/dst/src_* | wc -l)" = "2" ]; check "keep=2 prunes to 2" $?
[ -d "$T/dst/other_20240101_000001" ]; check "other prefixes untouched" $?
[ ! -d "$T/dst/src_20240101_000001" ]; check "oldest removed" $?

# 5. log file (wait so the folder name differs from the previous run)
sleep 1.1
"$BIN" --source "$T/src" --target "$T/dst" --once --log-file "$T/log.txt" >/dev/null 2>&1
grep -q "백업 완료" "$T/log.txt"; check "log file written" $?

# 6. bad interval
"$BIN" --source "$T/src" --target "$T/dst" --interval abc >/dev/null 2>&1; check "bad interval rejected" $([ $? -ne 0 ]; echo $?)

# 7. loop mode runs repeatedly and stops on SIGINT
rm -rf "$T/dst"; mkdir "$T/dst"
"$BIN" --source "$T/src" --target "$T/dst" --interval 1s > "$T/loop" 2>&1 &
P=$!; sleep 3.5; kill -INT $P; wait $P 2>/dev/null
n=$(ls "$T/dst" | wc -l); [ "$n" -ge 2 ]; check "loop made >=2 backups (got $n)" $?
grep -q "중지" "$T/loop"; check "stop message on SIGINT" $?

exit $fail
