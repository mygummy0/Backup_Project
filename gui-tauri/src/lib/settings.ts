import { COPY } from "@/lib/copy"

export interface Settings {
  source: string
  target: string
  interval: string
  keep: string
  incremental: boolean
  verify: boolean
  excludes: string
}

export const INTERVALS: Record<string, number> = Object.fromEntries(
  COPY.intervalOptions.map((o) => [o.label, o.seconds]),
)

export const KEEPS: Record<string, number> = Object.fromEntries(
  COPY.keepOptions.map((o) => [o.label, o.count]),
)

export const DEFAULT_SETTINGS: Settings = {
  source: "",
  target: "",
  interval: COPY.defaultInterval,
  keep: COPY.defaultKeep,
  incremental: false,
  verify: false,
  excludes: "",
}

const KEY = "auto-backup.settings"

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : DEFAULT_SETTINGS
  } catch {
    return DEFAULT_SETTINGS
  }
}

export function saveSettings(settings: Settings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings))
  } catch {
    /* 저장소를 쓸 수 없어도 앱은 동작해야 한다 */
  }
}
