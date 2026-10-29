// Design System v1.0 Applied
import { COPY } from "@/lib/copy"

/** 백업 중에만 움직이는 얇은 진행 표시줄. 움직임 줄이기 설정이면 정지한다. */
export function BusyBar({ active }: { active: boolean }) {
  return (
    <div
      role="progressbar"
      aria-label={COPY.progressLabel}
      aria-busy={active}
      className="h-1 w-full overflow-hidden rounded-full bg-border"
    >
      {active && <div className="busy-slide h-full w-1/3 rounded-full bg-primary" />}
    </div>
  )
}
