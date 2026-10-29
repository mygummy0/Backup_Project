// Design System v1.0 Applied
// Anti-Slop Rules Applied
import { useEffect, useState } from "react"
import { BusyBar } from "@/components/BusyBar"
import { FolderField } from "@/components/FolderField"
import { LogPanel } from "@/components/LogPanel"
import { SettingsDialog } from "@/components/SettingsDialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useBackup } from "@/hooks/useBackup"
import { useTheme } from "@/hooks/useTheme"
import { backend } from "@/lib/backend"
import { COPY } from "@/lib/copy"
import { formatRemaining } from "@/lib/format"
import { loadSettings, saveSettings } from "@/lib/settings"
import type { Settings } from "@/lib/settings"
import { cn } from "@/lib/utils"

export default function App() {
  useTheme()
  const [settings, setSettings] = useState<Settings>(loadSettings)
  const { running, busy, remaining, logs, invalid, clearInvalid, start, stop } = useBackup(settings)

  useEffect(() => saveSettings(settings), [settings])

  function patch<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((current) => ({ ...current, [key]: value }))
    if (key === "source" || key === "target") clearInvalid() // 입력을 고치면 오류가 사라진다
  }

  async function pick(key: "source" | "target") {
    const folder = await backend.pickFolder()
    if (folder) patch(key, folder)
  }

  const flagged = (field: "source" | "target") => invalid?.field === field || invalid?.field === "both"

  return (
    <main className="mx-auto flex h-full max-w-xl flex-col gap-6 overflow-y-auto p-8">
      <h1 className="sr-only">{COPY.title}</h1>

      <div className="flex justify-end">
        <SettingsDialog settings={settings} locked={running} onChange={patch} />
      </div>

      <Card>
        <CardContent className="flex flex-col gap-6">
          <h2 className="sr-only">{COPY.settingsHeading}</h2>
          <FolderField
            id="source"
            label={COPY.source.label}
            value={settings.source}
            invalid={flagged("source")}
            disabled={running}
            onChange={(value) => patch("source", value)}
            onPick={() => pick("source")}
          />
          <FolderField
            id="target"
            label={COPY.target.label}
            value={settings.target}
            invalid={flagged("target")}
            disabled={running}
            onChange={(value) => patch("target", value)}
            onPick={() => pick("target")}
          />
          <p id="form-error" role="alert" className="min-h-4 text-xs text-destructive">
            {invalid?.message}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-6">
          <h2 className="sr-only">{COPY.runHeading}</h2>
          <div className="flex items-center justify-between gap-4">
            <span
              className={cn("text-4xl font-light tabular-nums", running ? "text-foreground" : "text-muted-foreground")}
              aria-live="off"
            >
              <span className="sr-only">{COPY.nextBackup}</span>
              {remaining === null ? COPY.idleTimer : formatRemaining(remaining)}
            </span>
            <Button
              type="button"
              variant={running ? "outline" : "default"}
              className="w-32"
              onClick={running ? stop : start}
            >
              {running ? COPY.stop : COPY.start}
            </Button>
          </div>
          <BusyBar active={busy} />
        </CardContent>
      </Card>

      <LogPanel logs={logs} busy={busy} />
    </main>
  )
}
