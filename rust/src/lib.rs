//! Backup engine shared by the CLI (`main.rs`) and the Tauri GUI. Behaviour follows SPEC.md.
use chrono::Local;
use std::fs::{self, File, OpenOptions};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Level {
    Info,
    Success,
    Warn,
    Error,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    Done,
    Cancelled,
    Failed,
}

#[derive(Clone, Debug, Default)]
pub struct Options {
    pub keep: usize,
    pub incremental: bool,
    /// Compiled with [`compile_excludes`].
    pub excludes: Vec<Vec<char>>,
    pub verify: bool,
    pub dry_run: bool,
}

/// A validation failure and which input caused it (`"source"`, `"target"` or `"both"`).
#[derive(Clone, Debug)]
pub struct Invalid {
    pub field: &'static str,
    pub message: String,
}

#[derive(Default)]
struct Stats {
    copied: u32,
    reused: u32,
    excluded: u32,
    skipped: u32,
    verified: u32,
}

enum CopyError {
    Cancelled,
    Failed(String),
}

impl From<std::io::Error> for CopyError {
    fn from(e: std::io::Error) -> Self {
        CopyError::Failed(e.to_string())
    }
}

pub fn parse_interval(s: &str) -> Result<Duration, String> {
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

pub fn readable_size(mut b: f64) -> String {
    for unit in ["B", "KB", "MB", "GB", "TB"] {
        if b < 1024.0 {
            return format!("{b:.1} {unit}");
        }
        b /= 1024.0;
    }
    format!("{b:.1} PB")
}

// ---- exclude globs (see SPEC.md) ----------------------------------------------------

pub fn compile_excludes<S: AsRef<str>>(patterns: &[S]) -> Vec<Vec<char>> {
    patterns
        .iter()
        .map(|p| p.as_ref().trim_matches('/').chars().collect())
        .collect()
}

/// '*' = any run of non-'/', '**' = any run incl. '/', '?' = one non-'/' char.
pub fn glob_match(p: &[char], s: &[char]) -> bool {
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

// ---- validation -----------------------------------------------------------------------

/// Rejects missing dirs and a target inside (or equal to) the source, which would recurse forever.
pub fn validate(src: &str, dst: &str) -> Result<(PathBuf, PathBuf), Invalid> {
    let bad = |field, message: String| Invalid { field, message };
    if src.is_empty() || dst.is_empty() {
        let field = match (src.is_empty(), dst.is_empty()) {
            (true, true) => "both",
            (true, false) => "source",
            _ => "target",
        };
        return Err(bad(
            field,
            "원본 폴더와 저장 폴더를 모두 선택해주세요.".into(),
        ));
    }
    let s = fs::canonicalize(src)
        .map_err(|_| bad("source", format!("원본 폴더가 존재하지 않습니다: {src}")))?;
    let d = fs::canonicalize(dst)
        .map_err(|_| bad("target", format!("저장 폴더가 존재하지 않습니다: {dst}")))?;
    if !s.is_dir() {
        return Err(bad(
            "source",
            format!("원본 폴더가 존재하지 않습니다: {src}"),
        ));
    }
    if !d.is_dir() {
        return Err(bad(
            "target",
            format!("저장 폴더가 존재하지 않습니다: {dst}"),
        ));
    }
    if d.starts_with(&s) {
        return Err(bad(
            "target",
            "저장 폴더가 원본 폴더 안에 있을 수 없습니다".into(),
        ));
    }
    Ok((s, d))
}

// ---- copying --------------------------------------------------------------------------

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
/// reuse. With `o.dry_run` nothing is written. The cancel flag is checked before every entry.
fn copy_tree(
    o: &Options,
    st: &mut Stats,
    cancel: &AtomicBool,
    src: &Path,
    dst: &Path,
    prev: Option<&Path>,
    rel: &str,
) -> Result<(), CopyError> {
    let mut entries: Vec<_> = fs::read_dir(src)?.collect::<Result<_, _>>()?;
    entries.sort_by_key(|e| e.file_name());
    for e in entries {
        if cancel.load(Ordering::Relaxed) {
            return Err(CopyError::Cancelled);
        }
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
        let meta = fs::symlink_metadata(&from)?;
        if meta.is_dir() {
            if !o.dry_run {
                fs::create_dir(&to)?;
            }
            let prev_sub = prev.map(|p| p.join(e.file_name()));
            copy_tree(o, st, cancel, &from, &to, prev_sub.as_deref(), &rel_path)?;
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
            copy_file(&from, &to, &meta)?;
            if o.verify {
                if !same_content(&from, &to)? {
                    return Err(CopyError::Failed(format!("검증 실패: {rel_path}")));
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
pub fn backup_names(dst: &Path, base: &str) -> Vec<String> {
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

fn prune(dst: &Path, base: &str, keep: usize, log: &mut dyn FnMut(Level, &str)) {
    if keep == 0 {
        return;
    }
    let mut names = backup_names(dst, base);
    while names.len() > keep {
        let old = names.remove(0);
        match fs::remove_dir_all(dst.join(&old)) {
            Ok(()) => log(Level::Info, &format!("🗑 오래된 백업 삭제: {old}")),
            Err(e) => log(
                Level::Error,
                &format!("❌ 오래된 백업 삭제 실패: {old} ({e})"),
            ),
        }
    }
}

/// Runs one backup. Log lines use the SPEC.md wording; `log` receives them without timestamps.
pub fn run_backup(
    src: &Path,
    dst: &Path,
    o: &Options,
    cancel: &AtomicBool,
    log: &mut dyn FnMut(Level, &str),
) -> Outcome {
    let base = src
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "backup".into());
    let name = format!("{base}_{}", Local::now().format("%Y%m%d_%H%M%S"));
    let fin = dst.join(&name);
    let partial = dst.join(format!("{name}.partial"));

    if fin.symlink_metadata().is_ok() {
        log(
            Level::Error,
            &format!("❌ 오류 발생: 이미 존재하는 백업입니다: {name}"),
        );
        return Outcome::Failed;
    }
    let prev = if o.incremental {
        backup_names(dst, &base).pop().map(|n| dst.join(n))
    } else {
        None
    };

    let mut st = Stats::default();
    if !o.dry_run {
        if let Err(e) = fs::create_dir(&partial) {
            log(Level::Error, &format!("❌ 오류 발생: {e}"));
            return Outcome::Failed;
        }
    }
    let copied = copy_tree(o, &mut st, cancel, src, &partial, prev.as_deref(), "");
    if let Err(e) = copied {
        if !o.dry_run {
            let _ = fs::remove_dir_all(&partial);
        }
        return match e {
            CopyError::Cancelled => {
                log(Level::Warn, "백업이 취소되었습니다.");
                Outcome::Cancelled
            }
            CopyError::Failed(msg) => {
                log(Level::Error, &format!("❌ 오류 발생: {msg}"));
                Outcome::Failed
            }
        };
    }
    if o.dry_run {
        log(Level::Info, &format!("🧪 [dry-run] 백업 계획: {name}"));
    } else {
        if let Err(e) = fs::rename(&partial, &fin) {
            let _ = fs::remove_dir_all(&partial);
            log(Level::Error, &format!("❌ 오류 발생: {e}"));
            return Outcome::Failed;
        }
        if o.verify {
            log(
                Level::Info,
                &format!("🔍 검증 완료: {}개 파일 일치", st.verified),
            );
        }
    }
    log(
        Level::Info,
        &format!(
            "📦 복사 {}개, 재사용 {}개, 제외 {}개",
            st.copied, st.reused, st.excluded
        ),
    );
    if st.skipped > 0 {
        log(
            Level::Warn,
            &format!("⚠ 심볼릭 링크/특수 파일 {}개는 건너뛰었습니다", st.skipped),
        );
    }
    if !o.dry_run {
        log(
            Level::Success,
            &format!(
                "✅ 백업 완료: {name} (폴더 용량: {})",
                readable_size(dir_size(dst) as f64)
            ),
        );
        prune(dst, &base, o.keep, log);
    }
    Outcome::Done
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicU32;

    static N: AtomicU32 = AtomicU32::new(0);

    /// A fresh scratch dir with `src/{a.txt,sub/b.txt}` and an empty `dst/`.
    fn scratch() -> (PathBuf, PathBuf, PathBuf) {
        let root = std::env::temp_dir().join(format!("backup-test-{}-{}", std::process::id(), N.fetch_add(1, Ordering::SeqCst)));
        let (src, dst) = (root.join("src"), root.join("dst"));
        fs::create_dir_all(src.join("sub")).unwrap();
        fs::create_dir_all(&dst).unwrap();
        fs::write(src.join("a.txt"), "hello").unwrap();
        fs::write(src.join("sub/b.txt"), "world").unwrap();
        (root, src, dst)
    }

    fn run(src: &Path, dst: &Path, o: &Options, cancel: &AtomicBool) -> (Outcome, Vec<(Level, String)>) {
        let mut lines = Vec::new();
        let out = run_backup(src, dst, o, cancel, &mut |l, m| lines.push((l, m.to_string())));
        (out, lines)
    }

    #[test]
    fn backup_copies_tree_and_leaves_no_partial() {
        let (root, src, dst) = scratch();
        let (out, lines) = run(&src, &dst, &Options::default(), &AtomicBool::new(false));
        assert_eq!(out, Outcome::Done);
        let names: Vec<_> = fs::read_dir(&dst).unwrap().flatten().map(|e| e.file_name().into_string().unwrap()).collect();
        assert_eq!(names.len(), 1);
        assert!(!names[0].ends_with(".partial"));
        assert_eq!(fs::read_to_string(dst.join(&names[0]).join("sub/b.txt")).unwrap(), "world");
        assert!(lines.iter().any(|(l, m)| *l == Level::Success && m.contains("백업 완료")));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn cancelled_backup_removes_its_partial_folder() {
        let (root, src, dst) = scratch();
        let (out, lines) = run(&src, &dst, &Options::default(), &AtomicBool::new(true));
        assert_eq!(out, Outcome::Cancelled);
        assert_eq!(fs::read_dir(&dst).unwrap().count(), 0);
        assert!(lines.iter().any(|(l, _)| *l == Level::Warn));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn validate_names_the_offending_field() {
        let (root, src, dst) = scratch();
        let s = src.to_str().unwrap();
        let d = dst.to_str().unwrap();
        assert_eq!(validate("", "").unwrap_err().field, "both");
        assert_eq!(validate("", d).unwrap_err().field, "source");
        assert_eq!(validate(s, "").unwrap_err().field, "target");
        assert_eq!(validate("/no/such/dir", d).unwrap_err().field, "source");
        assert_eq!(validate(s, s).unwrap_err().field, "target");
        assert_eq!(validate(s, src.join("sub").to_str().unwrap()).unwrap_err().field, "target");
        assert!(validate(s, d).is_ok());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn exclude_globs_follow_the_spec() {
        let m = |pat: &str, s: &str| glob_match(&pat.chars().collect::<Vec<_>>(), &s.chars().collect::<Vec<_>>());
        assert!(m("*.log", "a.log") && !m("*.log", "dir/a.log"));
        assert!(m("docs/**/c.md", "docs/a/b/c.md") && m("file?.tmp", "file1.tmp") && !m("file?.tmp", "file12.tmp"));
        assert!(m("파일?이름.txt", "파일가이름.txt"));
    }

    #[test]
    fn parse_interval_rejects_bad_input() {
        assert_eq!(parse_interval("30s").unwrap(), Duration::from_secs(30));
        assert!(parse_interval("0s").is_err() && parse_interval("5").is_err() && parse_interval("-5m").is_err());
    }
}
