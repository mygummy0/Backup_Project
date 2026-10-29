import { useCallback, useEffect, useRef, useState } from "react"
import { backend } from "@/lib/backend"
import type { BackupOptions, Invalid, LogEntry } from "@/lib/backend"
import { COPY } from "@/lib/copy"
import { cleanMessage, conciseMessage, formatClock } from "@/lib/format"
import { INTERVALS, KEEPS } from "@/lib/settings"
import type { Settings } from "@/lib/settings"

export interface LogLine extends LogEntry {
  id: number
  time: string
}

function toOptions(s: Settings): BackupOptions {
  return {
    source: s.source,
    target: s.target,
    keep: KEEPS[s.keep] ?? 0,
    incremental: s.incremental,
    verify: s.verify,
    excludes: s.excludes.split("\n").map((l) => l.trim()).filter(Boolean),
  }
}

/** 시작/중지, 카운트다운, 주기 실행, 로그를 관리한다. 백업 자체는 Rust 엔진이 한다. */
export function useBackup(settings: Settings) {
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [remaining, setRemaining] = useState<number | null>(null)
  const [logs, setLogs] = useState<LogLine[]>([])
  const [invalid, setInvalid] = useState<Invalid | null>(null)

  const nextAt = useRef(0)
  const busyRef = useRef(false)
  const lineId = useRef(0)
  const snapshot = useRef(settings) // 실행 중에는 시작 시점의 설정을 쓴다

  const log = useCallback((entry: LogEntry) => {
    const line: LogLine = {
      ...entry,
      message: conciseMessage(cleanMessage(entry.message)),
      id: lineId.current++,
      time: formatClock(new Date()),
    }
    setLogs((prev) => [...prev, line])
  }, [])

  const runOnce = useCallback(async () => {
    if (busyRef.current) {
      log({ level: "warn", message: COPY.log.skippedBusy })
      return
    }
    busyRef.current = true
    setBusy(true)
    try {
      await backend.run(toOptions(snapshot.current), log)
    } catch (error) {
      log({ level: "error", message: COPY.log.error(String(error)) })
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }, [log])

  const start = useCallback(async () => {
    const problem = await backend.validate(settings.source, settings.target)
    setInvalid(problem)
    if (problem) return
    snapshot.current = settings
    const seconds = INTERVALS[settings.interval] ?? 300
    log({ level: "info", message: COPY.log.started(settings.interval) })
    nextAt.current = Date.now() + seconds * 1000
    setRemaining(seconds)
    setRunning(true)
    void runOnce()
  }, [settings, log, runOnce])

  const stop = useCallback(() => {
    setRunning(false)
    setRemaining(null)
    void backend.cancel() // 진행 중인 복사도 중단한다
    log({ level: "info", message: COPY.log.stopped })
  }, [log])

  useEffect(() => {
    if (!running) return
    const seconds = INTERVALS[snapshot.current.interval] ?? 300
    const timer = window.setInterval(() => {
      const left = Math.ceil((nextAt.current - Date.now()) / 1000)
      if (left <= 0) {
        nextAt.current += seconds * 1000
        setRemaining(seconds)
        void runOnce()
      } else {
        setRemaining(left)
      }
    }, 250)
    return () => window.clearInterval(timer)
  }, [running, runOnce])

  const clearInvalid = useCallback(() => setInvalid(null), [])

  return { running, busy, remaining, logs, invalid, clearInvalid, start, stop }
}
