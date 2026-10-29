import { Channel, invoke } from "@tauri-apps/api/core"
import { open } from "@tauri-apps/plugin-dialog"

export type Level = "info" | "success" | "warn" | "error"
export type Outcome = "done" | "cancelled" | "failed" | "busy"

export interface LogEntry {
  level: Level
  message: string
}

export interface BackupOptions {
  source: string
  target: string
  keep: number
  incremental: boolean
  verify: boolean
  excludes: string[]
}

export interface Invalid {
  field: "source" | "target" | "both"
  message: string
}

export interface Backend {
  validate(source: string, target: string): Promise<Invalid | null>
  run(options: BackupOptions, onLog: (entry: LogEntry) => void): Promise<Outcome>
  cancel(): Promise<void>
  pickFolder(): Promise<string | null>
}

/** Rust 엔진(backup crate)을 호출하는 실제 구현 */
const tauriBackend: Backend = {
  validate: (source, target) => invoke<Invalid | null>("validate_paths", { source, target }),
  async run(options, onLog) {
    const channel = new Channel<LogEntry>()
    channel.onmessage = onLog
    return invoke<Outcome>("run_backup", { options, onLog: channel })
  },
  cancel: () => invoke("cancel_backup"),
  async pickFolder() {
    const picked = await open({ directory: true, multiple: false })
    return typeof picked === "string" ? picked : null
  },
}

/** 브라우저에서 화면만 확인할 때(npm run dev, 테스트) 쓰는 메모리 구현. 파일을 건드리지 않는다. */
function createMockBackend(): Backend {
  let cancelled = false
  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
  return {
    async validate(source, target) {
      if (!source || !target) {
        const field = !source && !target ? "both" : !source ? "source" : "target"
        return { field, message: "원본 폴더와 저장 폴더를 모두 선택해주세요." }
      }
      if (target.startsWith(source + "/")) {
        return { field: "target", message: "저장 폴더가 원본 폴더 안에 있을 수 없습니다" }
      }
      return null
    },
    async run(options, onLog) {
      cancelled = false
      const name = `${options.source.split("/").filter(Boolean).pop() ?? "backup"}_20261029_090516`
      for (const ms of [700, 700, 700]) {
        await sleep(ms)
        if (cancelled) {
          onLog({ level: "warn", message: "백업이 취소되었습니다." })
          return "cancelled"
        }
      }
      onLog({ level: "info", message: "\u{1F4E6} 복사 12개, 재사용 0개, 제외 0개" })
      onLog({ level: "success", message: `\u2705 백업 완료: ${name} (폴더 용량: 31.0 B)` })
      return "done"
    },
    async cancel() {
      cancelled = true
    },
    async pickFolder() {
      return "/home/user/Documents"
    },
  }
}

const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window
export const backend: Backend = inTauri ? tauriBackend : createMockBackend()
