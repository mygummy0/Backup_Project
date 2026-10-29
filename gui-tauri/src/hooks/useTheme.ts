import { useEffect } from "react"

/** OS의 라이트/다크 설정을 따른다 (실행 중 바뀌어도 즉시 반영). BACKUP_THEME 대신 ?theme=dark 로 강제할 수 있다. */
export function useTheme() {
  useEffect(() => {
    const forced = new URLSearchParams(window.location.search).get("theme")
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const apply = () =>
      document.documentElement.classList.toggle("dark", forced ? forced === "dark" : media.matches)
    apply()
    media.addEventListener("change", apply)
    return () => media.removeEventListener("change", apply)
  }, [])
}
