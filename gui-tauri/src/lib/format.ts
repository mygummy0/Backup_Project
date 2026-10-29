/** 엔진 로그의 앞쪽 이모지·기호를 제거한다 (UI에서는 이모지를 쓰지 않는다). */
export function cleanMessage(message: string): string {
  return message.replace(/^[^\p{L}\p{N}[]+/u, "")
}

const pad2 = (n: number) => String(n).padStart(2, "0")

/** HH:MM:SS (로케일에 따라 달라지지 않게 직접 만든다) */
/** 엔진 문구(SPEC.md)는 그대로 두고 화면에만 짧게 보여 준다. */
export function conciseMessage(message: string): string {
  const done = message.match(/^백업 완료: (\S+) \(폴더 용량: (.+)\)$/)
  if (done) return `완료 ${done[1]} ${done[2]}`
  if (message === "백업이 취소되었습니다.") return "취소"
  return message
}

export function formatClock(date: Date): string {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
}

export function formatRemaining(seconds: number): string {
  return `${pad2(Math.floor(seconds / 60))}:${pad2(seconds % 60)}`
}
