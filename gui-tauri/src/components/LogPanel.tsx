// Design System v1.0 Applied
// Anti-Slop Rules Applied
import { useEffect, useRef } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { LogLine } from "@/hooks/useBackup"
import type { Level } from "@/lib/backend"
import { COPY } from "@/lib/copy"
import { cn } from "@/lib/utils"

const LEVEL_CLASS: Record<Level, string> = {
  info: "text-foreground",
  success: "text-success",
  warn: "text-warning",
  error: "text-destructive",
}

/** 작업 기록. 백업이 진행되는 동안에는 결과가 들어올 자리에 Skeleton을 보여 준다. */
export function LogPanel({ logs, busy }: { logs: LogLine[]; busy: boolean }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" })
  }, [logs.length, busy])

  return (
    <Card className="min-h-56 flex-1">
      <CardContent className="flex min-h-0 flex-1 flex-col">
        <h2 className="sr-only">{COPY.history}</h2>
        <div
          role="log"
          aria-live="polite"
          className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto rounded-lg bg-muted p-4 text-sm"
        >
          {logs.map((line) => (
            <p key={line.id}>
              <span className="mr-2 text-muted-foreground">{line.time}</span>
              <span className={cn(LEVEL_CLASS[line.level])}>{line.message}</span>
            </p>
          ))}
          {busy && <Skeleton className="mt-1 h-4 w-2/3" aria-hidden />}
          <div ref={end} />
        </div>
      </CardContent>
    </Card>
  )
}
