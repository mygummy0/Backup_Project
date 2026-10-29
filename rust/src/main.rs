use chrono::Local;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::exit;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::Duration;

struct Logger {
    file: Option<Mutex<File>>,
}

impl Logger {
    fn log(&self, msg: &str) {
        let line = format!("[{}] {}", Local::now().format("%H:%M:%S"), msg);
        println!("{line}");
        if let Some(f) = &self.file {
            let _ = writeln!(f.lock().unwrap(), "{line}");
        }
    }
}

struct Args {
    source: String,
    target: String,
    interval: Duration,
    interval_str: String,
    keep: usize,
    once: bool,
    incremental: bool,
    excludes: Vec<Vec<char>>,
    verify: bool,
    dry_run: bool,
    log_file: Option<String>,
}

struct Options {
    keep: usize,
    incremental: bool,
    excludes: Vec<Vec<char>>,
    verify: bool,
    dry_run: bool,
}

#[derive(Default)]
struct Stats {
    copied: u32,
    reused: u32,
    excluded: u32,
    skipped: u32,
    verified: u32,
}

fn usage() -> ! {
    eprintln!(
        "사용법: backup --source <폴더> --target <폴더> [--interval 5m] [--keep N] [--once]\n\
         \x20              [--mode full|incremental] [--exclude <글롭>]... [--verify] [--dry-run] [--log-file <파일>]"
    );
    exit(2)
}

fn usage_error(msg: &str) -> ! {
    eprintln!("{msg}");
    usage()
}

fn parse_interval(s: &str) -> Result<Duration, String> {
    let bad = || format!("잘못된 주기: {s:?} (예: 30s, 5m, 1h)");
    if s.len() < 2 || !s.is_char_boundary(s.len() - 1) {
        return Err(bad());
    }
    let (num, unit) = s.split_at(s.len() - 1);
    let n: u64 = num.parse().map_err(|_| bad())?;
    if n == 0 {
        return Err(bad());
    }
    match unit {
        "s" => Ok(Duration::from_secs(n)),
        "m" => Ok(Duration::from_secs(n * 60)),
        "h" => Ok(Duration::from_secs(n * 3600)),
        _ => Err(bad()),
    }
}

fn parse_args() -> Args {
    let mut source = None;
    let mut target = None;
    let mut interval_str = "5m".to_string();
    let mut keep = 0usize;
    let mut once = false;
    let mut incremental = false;
    let mut excludes = Vec::new();
    let mut verify = false;
    let mut dry_run = false;
    let mut log_file = None;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        let mut val = |name: &str| {
            it.next()
                .unwrap_or_else(|| usage_error(&format!("--{name} 에 값이 필요합니다.")))
        };
        match a.trim_start_matches('-') {
            "source" => source = Some(val("source")),
            "target" => target = Some(val("target")),
            "interval" => interval_str = val("interval"),
            "keep" => {
                keep = val("keep")
                    .parse()
                    .unwrap_or_else(|_| usage_error("--keep 은 0 이상의 정수여야 합니다."))
            }
            "mode" => match val("mode").as_str() {
                "full" => incremental = false,
                "incremental" => incremental = true,
                m => usage_error(&format!("잘못된 모드: {m:?} (full 또는 incremental)")),
            },
            "exclude" => excludes.push(val("exclude").trim_matches('/').chars().collect()),
            "once" => once = true,
            "verify" => verify = true,
            "dry-run" => dry_run = true,
            "log-file" => log_file = Some(val("log-file")),
            _ => usage(),
        }
    }
    let (Some(source), Some(target)) = (source, target) else {
        usage_error("--source 와 --target 은 필수입니다.")
    };
    let interval = parse_interval(&interval_str).unwrap_or_else(|e| usage_error(&e));
    Args {
        source,
        target,
        interval,
        interval_str,
        keep,
        once,
        incremental,
        excludes,
        verify,
        dry_run,
        log_file,
    }
}

fn readable_size(mut b: f64) -> String {
    for unit in ["B", "KB", "MB", "GB", "TB"] {
        if b < 1024.0 {
            return format!("{b:.1} {unit}");
        }
        b /= 1024.0;
    }
    format!("{b:.1} PB")
}

// ---- exclude globs (see SPEC.md) ----------------------------------------------

/// '*' = any run of non-'/', '**' = any run incl. '/', '?' = one non-'/' char.
fn glob_match(p: &[char], s: &[char]) -> bool {
    match p.first() {
        None => s.is_empty(),
        Some('*') => {
            let deep = p.get(1) == Some(&'*');
            let rest = &p[if deep { 2 } else { 1 }..];
            let mut i = 0;
            loop {
                if glob_match(rest, &s[i..]) {
                    return true;
                }
                if i >= s.len() || (!deep && s[i] == '/') {
                    return false;
                }
                i += 1;
            }
        }
        Some('?') => !s.is_empty() && s[0] != '/' && glob_match(&p[1..], &s[1..]),
        Some(c) => !s.is_empty() && s[0] == *c && glob_match(&p[1..], &s[1..]),
    }
}

fn is_excluded(patterns: &[Vec<char>], rel: &str, name: &str) -> bool {
    patterns.iter().any(|p| {
        if p.is_empty() {
            return false;
        }
        let target = if p.contains(&'/') { rel } else { name };
        glob_match(p, &target.chars().collect::<Vec<_>>())
    })
}

// ---- validation -----------------------------------------------------------------

/// Rejects missing dirs and a target inside (or equal to) the source, which would recurse forever.
fn validate(src: &str, dst: &str) -> Result<(PathBuf, PathBuf), String> {
    let s = fs::canonicalize(src).map_err(|_| format!("원본 폴더가 존재하지 않습니다: {src}"))?;
    let d = fs::canonicalize(dst).map_err(|_| format!("저장 폴더가 존재하지 않습니다: {dst}"))?;
    if !s.is_dir() {
        return Err(format!("원본 폴더가 존재하지 않습니다: {src}"));
    }
    if !d.is_dir() {
        return Err(format!("저장 폴더가 존재하지 않습니다: {dst}"));
    }
    if d.starts_with(&s) {
        return Err("저장 폴더가 원본 폴더 안에 있을 수 없습니다".into());
    }
    Ok((s, d))
}

// ---- copying --------------------------------------------------------------------

fn same_content(a: &Path, b: &Path) -> std::io::Result<bool> {
    let (mut fa, mut fb) = (File::open(a)?, File::open(b)?);
    let (mut ba, mut bb) = (vec![0u8; 64 << 10], vec![0u8; 64 << 10]);
    loop {
        let na = read_full(&mut fa, &mut ba)?;
        let nb = read_full(&mut fb, &mut bb)?;
        if na != nb || ba[..na] != bb[..nb] {
            return Ok(false);
        }
        if na < ba.len() {
            return Ok(true);
        }
    }
}

fn read_full(f: &mut File, buf: &mut [u8]) -> std::io::Result<usize> {
    let mut n = 0;
    while n < buf.len() {
        match f.read(&mut buf[n..])? {
            0 => break,
            k => n += k,
        }
    }
    Ok(n)
}

fn copy_file(from: &Path, to: &Path, meta: &fs::Metadata) -> std::io::Result<()> {
    // create_new: never overwrite an existing file
    let mut out = OpenOptions::new().write(true).create_new(true).open(to)?;
    std::io::copy(&mut File::open(from)?, &mut out)?;
    out.set_modified(meta.modified()?)?;
    drop(out);
    fs::set_permissions(to, meta.permissions())
}

/// Mirrors `src` into `dst`. `prev` (may be None) is the previous snapshot used for incremental
/// reuse. With `o.dry_run` nothing is written.
fn copy_tree(
    o: &Options,
    st: &mut Stats,
    src: &Path,
    dst: &Path,
    prev: Option<&Path>,
    rel: &str,
) -> Result<(), String> {
    let mut entries: Vec<_> = fs::read_dir(src)
        .map_err(|e| e.to_string())?
        .collect::<Result<_, _>>()
        .map_err(|e| e.to_string())?;
    entries.sort_by_key(|e| e.file_name());
    for e in entries {
        let name = e.file_name().to_string_lossy().into_owned();
        let rel_path = if rel.is_empty() {
            name.clone()
        } else {
            format!("{rel}/{name}")
        };
        if is_excluded(&o.excludes, &rel_path, &name) {
            st.excluded += 1;
            continue;
        }
        let from = e.path();
        let to = dst.join(e.file_name());
        let meta = fs::symlink_metadata(&from).map_err(|e| e.to_string())?;
        if meta.is_dir() {
            if !o.dry_run {
                fs::create_dir(&to).map_err(|e| e.to_string())?;
            }
            let prev_sub = prev.map(|p| p.join(e.file_name()));
            copy_tree(o, st, &from, &to, prev_sub.as_deref(), &rel_path)?;
        } else if meta.is_file() {
            if let Some(p) = prev.map(|p| p.join(e.file_name())) {
                if let Ok(pm) = fs::symlink_metadata(&p) {
                    let unchanged = pm.is_file()
                        && pm.len() == meta.len()
                        && pm.modified().ok() == meta.modified().ok();
                    if unchanged && (o.dry_run || fs::hard_link(&p, &to).is_ok()) {
                        st.reused += 1;
                        continue;
                    }
                }
            }
            st.copied += 1;
            if o.dry_run {
                continue;
            }
            copy_file(&from, &to, &meta).map_err(|e| e.to_string())?;
            if o.verify {
                if !same_content(&from, &to).map_err(|e| e.to_string())? {
                    return Err(format!("검증 실패: {rel_path}"));
                }
                st.verified += 1;
            }
        } else {
            st.skipped += 1;
        }
    }
    Ok(())
}

fn dir_size(root: &Path) -> u64 {
    let mut total = 0;
    if let Ok(rd) = fs::read_dir(root) {
        for e in rd.flatten() {
            if let Ok(ft) = e.file_type() {
                if ft.is_dir() {
                    total += dir_size(&e.path());
                } else if ft.is_file() {
                    total += e.metadata().map(|m| m.len()).unwrap_or(0);
                }
            }
        }
    }
    total
}

fn is_backup_name(name: &str, base: &str) -> bool {
    let Some(rest) = name.strip_prefix(base).and_then(|r| r.strip_prefix('_')) else {
        return false;
    };
    let b = rest.as_bytes();
    b.len() == 15
        && b[8] == b'_'
        && b.iter()
            .enumerate()
            .all(|(i, c)| i == 8 || c.is_ascii_digit())
}

/// Complete backups of `base` in `dst`, oldest first (".partial" dirs never match).
fn backup_names(dst: &Path, base: &str) -> Vec<String> {
    let Ok(rd) = fs::read_dir(dst) else {
        return Vec::new();
    };
    let mut names: Vec<String> = rd
        .flatten()
        .filter(|e| e.file_type().map(|t| t.is_dir()).unwrap_or(false))
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| is_backup_name(n, base))
        .collect();
    names.sort();
    names
}

fn prune(dst: &Path, base: &str, keep: usize, log: &Logger) {
    if keep == 0 {
        return;
    }
    let mut names = backup_names(dst, base);
    while names.len() > keep {
        let old = names.remove(0);
        match fs::remove_dir_all(dst.join(&old)) {
            Ok(()) => log.log(&format!("🗑 오래된 백업 삭제: {old}")),
            Err(e) => log.log(&format!("❌ 오래된 백업 삭제 실패: {old} ({e})")),
        }
    }
}

fn run_backup(src: &Path, dst: &Path, o: &Options, log: &Logger) -> bool {
    let base = src
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "backup".into());
    let name = format!("{base}_{}", Local::now().format("%Y%m%d_%H%M%S"));
    let fin = dst.join(&name);
    let partial = dst.join(format!("{name}.partial"));

    if fin.symlink_metadata().is_ok() {
        log.log(&format!("❌ 오류 발생: 이미 존재하는 백업입니다: {name}"));
        return false;
    }
    let prev = if o.incremental {
        backup_names(dst, &base).pop().map(|n| dst.join(n))
    } else {
        None
    };

    let mut st = Stats::default();
    if !o.dry_run {
        if let Err(e) = fs::create_dir(&partial) {
            log.log(&format!("❌ 오류 발생: {e}"));
            return false;
        }
    }
    if let Err(e) = copy_tree(o, &mut st, src, &partial, prev.as_deref(), "") {
        if !o.dry_run {
            let _ = fs::remove_dir_all(&partial);
        }
        log.log(&format!("❌ 오류 발생: {e}"));
        return false;
    }
    if o.dry_run {
        log.log(&format!("🧪 [dry-run] 백업 계획: {name}"));
    } else {
        if let Err(e) = fs::rename(&partial, &fin) {
            let _ = fs::remove_dir_all(&partial);
            log.log(&format!("❌ 오류 발생: {e}"));
            return false;
        }
        if o.verify {
            log.log(&format!("🔍 검증 완료: {}개 파일 일치", st.verified));
        }
    }
    log.log(&format!(
        "📦 복사 {}개, 재사용 {}개, 제외 {}개",
        st.copied, st.reused, st.excluded
    ));
    if st.skipped > 0 {
        log.log(&format!(
            "⚠ 심볼릭 링크/특수 파일 {}개는 건너뛰었습니다",
            st.skipped
        ));
    }
    if !o.dry_run {
        log.log(&format!(
            "✅ 백업 완료: {name} (폴더 용량: {})",
            readable_size(dir_size(dst) as f64)
        ));
        prune(dst, &base, o.keep, log);
    }
    true
}

fn main() {
    let args = parse_args();
    let (src, dst) = validate(&args.source, &args.target).unwrap_or_else(|e| {
        eprintln!("❌ {e}");
        exit(1)
    });
    let file = args.log_file.as_ref().map(|p| {
        let f = OpenOptions::new()
            .create(true)
            .append(true)
            .open(p)
            .unwrap_or_else(|e| {
                eprintln!("❌ 로그 파일을 열 수 없습니다: {e}");
                exit(1)
            });
        Mutex::new(f)
    });
    let log = Logger { file };
    let opts = Options {
        keep: args.keep,
        incremental: args.incremental,
        excludes: args.excludes,
        verify: args.verify,
        dry_run: args.dry_run,
    };

    if args.once || args.dry_run {
        exit(if run_backup(&src, &dst, &opts, &log) {
            0
        } else {
            1
        });
    }

    let stop = Arc::new(AtomicBool::new(false));
    let (tx, rx) = mpsc::channel::<()>();
    {
        let stop = stop.clone();
        ctrlc::set_handler(move || {
            stop.store(true, Ordering::SeqCst);
            let _ = tx.send(());
        })
        .expect("Ctrl-C 핸들러 설정 실패");
    }

    log.log(&format!("자동 백업 시작됨 (주기: {})", args.interval_str));
    loop {
        run_backup(&src, &dst, &opts, &log);
        // wakes immediately on Ctrl-C/SIGTERM instead of sleeping out the interval
        let _ = rx.recv_timeout(args.interval);
        if stop.load(Ordering::SeqCst) {
            log.log("자동 백업이 사용자에 의해 중지되었습니다.");
            return;
        }
    }
}
