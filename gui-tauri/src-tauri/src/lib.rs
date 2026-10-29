//! Tauri 명령: 프런트(React)와 `backup` 엔진을 잇는 얇은 층. 백업 규칙은 모두 엔진(rust/src/lib.rs)에 있다.
use backup::{compile_excludes, Level, Options, Outcome};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::ipc::Channel;
use tauri::State;

#[derive(Default)]
struct AppState {
    /// 진행 중인 백업을 취소하라는 신호 (엔진이 파일마다 확인한다)
    cancel: Arc<AtomicBool>,
    /// 동시에 두 백업이 돌지 않게 하는 가드
    busy: Mutex<bool>,
}

#[derive(Serialize, Clone)]
struct LogEntry {
    level: &'static str,
    message: String,
}

#[derive(Serialize)]
struct InvalidDto {
    field: &'static str,
    message: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct BackupArgs {
    source: String,
    target: String,
    keep: usize,
    incremental: bool,
    verify: bool,
    excludes: Vec<String>,
}

fn level_name(level: Level) -> &'static str {
    match level {
        Level::Info => "info",
        Level::Success => "success",
        Level::Warn => "warn",
        Level::Error => "error",
    }
}

fn outcome_name(outcome: Outcome) -> &'static str {
    match outcome {
        Outcome::Done => "done",
        Outcome::Cancelled => "cancelled",
        Outcome::Failed => "failed",
    }
}

/// 문제가 있으면 어떤 입력이 문제인지(`source`/`target`/`both`)와 메시지를 돌려준다.
#[tauri::command]
fn validate_paths(source: String, target: String) -> Option<InvalidDto> {
    backup::validate(&source, &target).err().map(|e| InvalidDto { field: e.field, message: e.message })
}

/// 백업을 한 번 실행한다. 로그는 `on_log` 채널로 실시간 전달하고 결과(`done`/`cancelled`/`failed`/`busy`)를 돌려준다.
#[tauri::command]
async fn run_backup(options: BackupArgs, on_log: Channel<LogEntry>, state: State<'_, AppState>) -> Result<&'static str, String> {
    {
        let mut busy = state.busy.lock().map_err(|e| e.to_string())?;
        if *busy {
            return Ok("busy");
        }
        *busy = true;
    }
    state.cancel.store(false, Ordering::SeqCst);
    let cancel = state.cancel.clone();

    let joined = tauri::async_runtime::spawn_blocking(move || {
        let mut emit = |level: Level, message: &str| {
            let _ = on_log.send(LogEntry { level: level_name(level), message: message.to_string() });
        };
        let (src, dst) = match backup::validate(&options.source, &options.target) {
            Ok(paths) => paths,
            Err(e) => {
                emit(Level::Error, &format!("오류: {}", e.message));
                return "failed";
            }
        };
        let opts = Options {
            keep: options.keep,
            incremental: options.incremental,
            excludes: compile_excludes(&options.excludes),
            verify: options.verify,
            dry_run: false,
        };
        outcome_name(backup::run_backup(&src, &dst, &opts, &cancel, &mut emit))
    })
    .await;

    if let Ok(mut busy) = state.busy.lock() {
        *busy = false;
    }
    joined.map_err(|e| e.to_string())
}

/// 진행 중인 백업을 취소한다 (엔진이 `.partial` 폴더를 정리한다).
#[tauri::command]
fn cancel_backup(state: State<'_, AppState>) {
    state.cancel.store(true, Ordering::SeqCst);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![validate_paths, run_backup, cancel_backup])
        .run(tauri::generate_context!())
        .expect("Tauri 앱을 시작하지 못했습니다");
}
