// Design System v1.0 Applied
import { ChevronDown } from "lucide-react"
import { useEffect, useState } from "react"
import { BusyBar } from "@/components/BusyBar"
import { FolderField } from "@/components/FolderField"
import { LogPanel } from "@/components/LogPanel"
import { OptionSelect } from "@/components/OptionSelect"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { useBackup } from "@/hooks/useBackup"
import { useTheme } from "@/hooks/useTheme"
import { backend } from "@/lib/backend"
import { COPY } from "@/lib/copy"
import { formatRemaining } from "@/lib/format"
import { INTERVALS, KEEPS, loadSettings, saveSettings } from "@/lib/settings"
import type { Settings } from "@/lib/settings"
import { cn } from "@/lib/utils"

export default function App() {
  useTheme()
  const [settings, setSettings] = useState<Settings>(loadSettings)
  const [advancedOpen, setAdvancedOpen] = useState(false)
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
    <main className="mx-auto flex h-full max-w-xl flex-col gap-4 overflow-y-auto p-6">
      <h1 className="text-2xl font-bold tracking-tight">{COPY.title}</h1>

      <Card>
        <CardContent className="flex flex-col gap-4">
          <FolderField
            id="source"
            label={COPY.source.label}
            value={settings.source}
            placeholder={COPY.source.placeholder}
            invalid={flagged("source")}
            disabled={running}
            onChange={(value) => patch("source", value)}
            onPick={() => pick("source")}
          />
          <FolderField
            id="target"
            label={COPY.target.label}
            value={settings.target}
            placeholder={COPY.target.placeholder}
            invalid={flagged("target")}
            disabled={running}
            onChange={(value) => patch("target", value)}
            onPick={() => pick("target")}
          />
          <div className="grid grid-cols-2 gap-4">
            <OptionSelect
              id="interval"
              label={COPY.interval}
              value={settings.interval}
              options={Object.keys(INTERVALS)}
              disabled={running}
              onChange={(value) => patch("interval", value)}
            />
            <OptionSelect
              id="keep"
              label={COPY.keep}
              value={settings.keep}
              options={Object.keys(KEEPS)}
              disabled={running}
              onChange={(value) => patch("keep", value)}
            />
          </div>

          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <CollapsibleTrigger asChild>
              <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
                {COPY.advanced}
                <ChevronDown className={cn("transition-transform duration-200 ease-out", advancedOpen && "rotate-180")} />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="flex flex-col gap-4 pt-4">
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="incremental" className="flex flex-col items-start gap-1">
                  {COPY.incremental.label}
                  <span className="text-xs font-normal text-muted-foreground">{COPY.incremental.hint}</span>
                </Label>
                <Switch
                  id="incremental"
                  checked={settings.incremental}
                  disabled={running}
                  onCheckedChange={(value) => patch("incremental", value)}
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="verify" className="flex flex-col items-start gap-1">
                  {COPY.verify.label}
                  <span className="text-xs font-normal text-muted-foreground">{COPY.verify.hint}</span>
                </Label>
                <Switch
                  id="verify"
                  checked={settings.verify}
                  disabled={running}
                  onCheckedChange={(value) => patch("verify", value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="excludes" className="text-xs font-medium text-muted-foreground">
                  {COPY.excludes.label}
                </Label>
                <Textarea
                  id="excludes"
                  value={settings.excludes}
                  placeholder={COPY.excludes.placeholder}
                  disabled={running}
                  onChange={(event) => patch("excludes", event.target.value)}
                />
              </div>
            </CollapsibleContent>
          </Collapsible>

          <p id="form-error" role="alert" className="min-h-4 text-xs text-destructive">
            {invalid?.message}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">{COPY.nextBackup}</span>
              <span
                className={cn(
                  "text-4xl font-bold tabular-nums",
                  running ? "text-foreground" : "text-muted-foreground",
                )}
                aria-live="off"
              >
                {remaining === null ? COPY.idleTimer : formatRemaining(remaining)}
              </span>
            </div>
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
