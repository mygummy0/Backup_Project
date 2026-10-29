// Design System v1.0 Applied
// Anti-Slop Rules Applied
import { Settings as SettingsIcon } from "lucide-react"
import { OptionSelect } from "@/components/OptionSelect"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { COPY } from "@/lib/copy"
import { INTERVALS, KEEPS } from "@/lib/settings"
import type { Settings } from "@/lib/settings"

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  settings: Settings
  locked: boolean
  onChange: <K extends keyof Settings>(key: K, value: Settings[K]) => void
}

/** 상단의 설정 창. 일반(주기·보관)과 고급 옵션(증분·검증·제외) 탭으로 나뉜다. 백업 중에는 값을 바꿀 수 없다. */
export function SettingsDialog({ open, onOpenChange, settings, locked, onChange }: SettingsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button type="button" variant="ghost" size="icon-sm" aria-label={COPY.settings}>
          <SettingsIcon />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{COPY.settings}</DialogTitle>
          <DialogDescription className="sr-only">{COPY.settingsHint}</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="general" className="gap-6">
          <TabsList variant="line">
            <TabsTrigger value="general">{COPY.tabs.general}</TabsTrigger>
            <TabsTrigger value="advanced">{COPY.tabs.advanced}</TabsTrigger>
          </TabsList>

          <TabsContent value="general" className="grid grid-cols-2 gap-6">
            <OptionSelect
              id="interval"
              label={COPY.interval}
              value={settings.interval}
              options={Object.keys(INTERVALS)}
              disabled={locked}
              onChange={(value) => onChange("interval", value)}
            />
            <OptionSelect
              id="keep"
              label={COPY.keep}
              value={settings.keep}
              options={Object.keys(KEEPS)}
              disabled={locked}
              onChange={(value) => onChange("keep", value)}
            />
          </TabsContent>

          <TabsContent value="advanced" className="flex flex-col gap-6">
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="incremental">{COPY.incremental.label}</Label>
              <Switch
                id="incremental"
                checked={settings.incremental}
                disabled={locked}
                onCheckedChange={(value) => onChange("incremental", value)}
              />
            </div>
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="verify">{COPY.verify.label}</Label>
              <Switch
                id="verify"
                checked={settings.verify}
                disabled={locked}
                onCheckedChange={(value) => onChange("verify", value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="excludes" className="text-xs text-muted-foreground">
                {COPY.excludes.label}
              </Label>
              <Textarea
                id="excludes"
                value={settings.excludes}
                placeholder={COPY.excludes.placeholder}
                disabled={locked}
                onChange={(event) => onChange("excludes", event.target.value)}
              />
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
