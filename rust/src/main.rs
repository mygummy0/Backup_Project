use chrono::Local;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
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
    log_file: Option<String>,
}

fn usage() -> ! {
    eprintln!(
        "사용법: backup --source <폴더> --target <폴더> [--interval 5m] [--keep N] [--once] [--log-file <파일>]"
    );
    exit(2)
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
    let mut log_file = None;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        let mut val = |name: &str| {
            it.next().unwrap_or_else(|| {
                eprintln!("{name} 에 값이 필요합니다.");
                usage()
            })
        };
        match a.as_str() {
            "--source" | "-source" => source = Some(val("--source")),
            "--target" | "-target" => target = Some(val("--target")),
            "--interval" | "-interval" => interval_str = val("--interval"),
            "--keep" | "-keep" => {
                keep = val("--keep").parse().unwrap_or_else(|_| {
                    eprintln!("--keep 은 0 이상의 정수여야 합니다.");
                    exit(2)
                })
            }
            "--once" | "-once" => once = true,
            "--log-file" | "-log-file" => log_file = Some(val("--log-file")),
            _ => usage(),
        }
    }
    let (Some(source), Some(target)) = (source, target) else {
        eprintln!("--source 와 --target 은 필수입니다.");
        usage()
    };
    let interval = parse_interval(&interval_str).unwrap_or_else(|e| {
        eprintln!("{e}");
        exit(2)
    });
    Args { source, target, interval, interval_str, keep, once, log_file }
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

fn copy_dir(src: &Path, dst: &Path, skipped: &mut u32) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let ft = entry.file_type()?;
        let to = dst.join(entry.file_name());
        if ft.is_dir() {
            copy_dir(&entry.path(), &to, skipped)?;
        } else if ft.is_file() {
            // create_new mirrors the Go version: never overwrite an existing backup
            let mut out = OpenOptions::new().write(true).create_new(true).open(&to)?;
            let mut inp = File::open(entry.path())?;
            std::io::copy(&mut inp, &mut out)?;
            fs::set_permissions(&to, entry.metadata()?.permissions())?;
        } else {
            *skipped += 1;
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
    b.len() == 15 && b[8] == b'_' && b.iter().enumerate().all(|(i, c)| i == 8 || c.is_ascii_digit())
}

fn prune(dst: &Path, base: &str, keep: usize, log: &Logger) {
    if keep == 0 {
        return;
    }
    let Ok(rd) = fs::read_dir(dst) else { return };
    let mut names: Vec<String> = rd
        .flatten()
        .filter(|e| e.file_type().map(|t| t.is_dir()).unwrap_or(false))
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| is_backup_name(n, base))
        .collect();
    names.sort();
    while names.len() > keep {
        let old = names.remove(0);
        match fs::remove_dir_all(dst.join(&old)) {
            Ok(()) => log.log(&format!("🗑 오래된 백업 삭제: {old}")),
            Err(e) => log.log(&format!("❌ 오래된 백업 삭제 실패: {old} ({e})")),
        }
    }
}

fn run_backup(src: &Path, dst: &Path, keep: usize, log: &Logger) {
    let base = src.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "backup".into());
    let name = format!("{base}_{}", Local::now().format("%Y%m%d_%H%M%S"));
    let mut skipped = 0;
    if let Err(e) = copy_dir(src, &dst.join(&name), &mut skipped) {
        log.log(&format!("❌ 오류 발생: {e}"));
        return;
    }
    log.log(&format!("✅ 백업 완료: {name} (폴더 용량: {})", readable_size(dir_size(dst) as f64)));
    if skipped > 0 {
        log.log(&format!("⚠ 심볼릭 링크/특수 파일 {skipped}개는 건너뛰었습니다"));
    }
    prune(dst, &base, keep, log);
}

fn main() {
    let args = parse_args();
    let (src, dst) = validate(&args.source, &args.target).unwrap_or_else(|e| {
        eprintln!("❌ {e}");
        exit(1)
    });
    let file = args.log_file.as_ref().map(|p| {
        let f = OpenOptions::new().create(true).append(true).open(p).unwrap_or_else(|e| {
            eprintln!("❌ 로그 파일을 열 수 없습니다: {e}");
            exit(1)
        });
        Mutex::new(f)
    });
    let log = Logger { file };

    if args.once {
        run_backup(&src, &dst, args.keep, &log);
        return;
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
        run_backup(&src, &dst, args.keep, &log);
        // wakes immediately on Ctrl-C instead of sleeping out the interval
        let _ = rx.recv_timeout(args.interval);
        if stop.load(Ordering::SeqCst) {
            log.log("자동 백업이 사용자에 의해 중지되었습니다.");
            return;
        }
    }
}
