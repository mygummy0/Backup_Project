/** 엔진 로그의 앞쪽 이모지·기호를 제거한다 (UI에서는 이모지를 쓰지 않는다). */
export function cleanMessage(message: string): string {
  return message.replace(/^[^\p{L}\p{N}[]+/u, "")
}

const pad2 = (n: number) => String(n).padStart(2, "0")

/** HH:MM:SS (로케일에 따라 달라지지 않게 직접 만든다) */
export function formatClock(date: Date): string {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
}

export function formatRemaining(seconds: number): string {
  return `${pad2(Math.floor(seconds / 60))}:${pad2(seconds % 60)}`
}
