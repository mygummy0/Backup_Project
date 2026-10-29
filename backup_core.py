"""GUI가 쓰는 백업 엔진 (tkinter에 의존하지 않아 단독으로 테스트할 수 있다).

SPEC.md 와 같은 규칙: `{원본명}_{YYYYMMDD_HHMMSS}.partial` 에 복사한 뒤 완료되면 이름을 바꾼다.
중간에 실패하거나 취소돼도 반쪽짜리 백업이 남지 않는다.
"""
import datetime
import os
import re
import shutil
import threading


class Cancelled(Exception):
    """사용자가 진행 중인 백업을 취소했다."""


def readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def folder_size(root):
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def run_backup(src, dst, cancel, now=None):
    """src 를 dst 아래에 백업하고 최종 폴더 이름을 돌려준다. 취소되면 Cancelled 를 던진다."""
    now = now or datetime.datetime.now()
    name = f"{os.path.basename(os.path.normpath(src))}_{now.strftime('%Y%m%d_%H%M%S')}"
    final = os.path.join(dst, name)
    partial = final + ".partial"
    if os.path.lexists(final):
        raise FileExistsError(f"이미 존재하는 백업입니다: {name}")

    def copy_file(s, d):
        if cancel.is_set():
            raise Cancelled()
        return shutil.copy2(s, d)

    try:
        shutil.copytree(src, partial, copy_function=copy_file)
        if cancel.is_set():
            raise Cancelled()
        os.rename(partial, final)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return name


def prune(dst, base, keep):
    """최근 keep 개만 남기고 오래된 백업을 지운다 (keep <= 0 이면 무제한). (삭제됨, 실패) 목록을 돌려준다."""
    if keep <= 0:
        return [], []
    pattern = re.compile(re.escape(base) + r"_\d{8}_\d{6}")  # ".partial" 폴더는 일치하지 않는다
    names = sorted(n for n in os.listdir(dst)
                   if pattern.fullmatch(n) and os.path.isdir(os.path.join(dst, n)))
    deleted, failed = [], []
    for old in names[:-keep]:
        try:
            shutil.rmtree(os.path.join(dst, old))
            deleted.append(old)
        except OSError as e:
            failed.append((old, e))
    return deleted, failed


def new_cancel_event():
    return threading.Event()
