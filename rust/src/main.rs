use backup::{compile_excludes, run_backup, validate, Options, Outcome};
use chrono::Local;
use std::fs::{File, OpenOptions};
use std::io::Write;
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
    excludes: Vec<String>,
    verify: bool,
    dry_run: bool,
    log_file: Option<String>,
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
            "exclude" => excludes.push(val("exclude")),
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
    let interval = backup::parse_interval(&interval_str).unwrap_or_else(|e| usage_error(&e));
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

fn main() {
    let args = parse_args();
    let (src, dst) = validate(&args.source, &args.target).unwrap_or_else(|e| {
        eprintln!("❌ {}", e.message);
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
        excludes: compile_excludes(&args.excludes),
        verify: args.verify,
        dry_run: args.dry_run,
    };

    // SIGINT/SIGTERM cancel a running copy (the engine removes its .partial folder) and end the loop
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
    let mut emit = |_: backup::Level, msg: &str| log.log(msg);

    if args.once || args.dry_run {
        exit(
            if run_backup(&src, &dst, &opts, &stop, &mut emit) == Outcome::Done {
                0
            } else {
                1
            },
        );
    }

    log.log(&format!("자동 백업 시작됨 (주기: {})", args.interval_str));
    loop {
        run_backup(&src, &dst, &opts, &stop, &mut emit);
        if !stop.load(Ordering::SeqCst) {
            // wakes immediately on Ctrl-C/SIGTERM instead of sleeping out the interval
            let _ = rx.recv_timeout(args.interval);
        }
        if stop.load(Ordering::SeqCst) {
            log.log("자동 백업이 사용자에 의해 중지되었습니다.");
            return;
        }
    }
}
