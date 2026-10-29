// 브라우저(목 백엔드)에서 화면 상태 6종 x 테마 2종을 캡처하고 접근성/상태를 값으로 검증한다.
// 사용: npm run build && npx vite preview --port 4173 &  →  node scripts/shots.mjs <출력폴더> [baseUrl]
import { createRequire } from "node:module"
import { mkdirSync } from "node:fs"
const require = createRequire(import.meta.url)
const { chromium } = require("playwright")

const out = process.argv[2] ?? "shots"
const base = process.argv[3] ?? "http://localhost:4173"
mkdirSync(out, { recursive: true })

const rgb = (hex) => {
  const n = parseInt(hex.slice(1), 16)
  return `rgb(${n >> 16}, ${(n >> 8) & 255}, ${n & 255})`
}
const checks = []
const check = (name, ok, detail = "") => {
  checks.push(ok)
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`)
}

const browser = await chromium.launch()
for (const theme of ["light", "dark"]) {
  const context = await browser.newContext({ viewport: { width: 640, height: 840 }, locale: "ko-KR" })
  const page = await context.newPage()
  await page.goto(`${base}/?theme=${theme}`)
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  const shot = (name) => page.screenshot({ path: `${out}/${theme}_${name}.png` })
  const start = page.getByRole("button", { name: "시작" })

  // 1 초기
  await shot("1_initial")

  // 접근성/상태 검증 (라이트에서 한 번)
  if (theme === "light") {
    const order = []
    await page.locator("body").click({ position: { x: 2, y: 2 } })
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press("Tab")
      order.push(await page.evaluate(() => {
        const el = document.activeElement
        return el.id || el.getAttribute("role") || el.textContent?.trim() || el.tagName
      }))
    }
    console.log("tab order:", order.join(" > "))
    check("Tab 순서 = 화면 순서", order.join(",") === "source,선택,target,선택,interval,keep,고급 옵션,시작")
    check("키보드 포커스 링(focus-visible)", await start.evaluate((el) => getComputedStyle(el).boxShadow !== "none"))
    check("전환 시간 200ms", await start.evaluate((el) => getComputedStyle(el).transitionDuration.includes("0.2s")))

    await page.mouse.move(0, 0)
    await start.hover()
    await page.waitForTimeout(350)
    check("hover = brand-700", (await start.evaluate((el) => getComputedStyle(el).backgroundColor)) === rgb("#4338CA"))
    await page.mouse.down()
    await page.waitForTimeout(350)
    check("active = brand-800", (await start.evaluate((el) => getComputedStyle(el).backgroundColor)) === rgb("#3730A3"))
    await page.mouse.up({ button: "left" }).catch(() => {})
    await page.mouse.move(0, 0)
  }

  // 2 입력 오류 (빈 폼에서 시작)
  await page.mouse.move(0, 0)
  await start.click()
  await page.waitForTimeout(300)
  await shot("2_error")
  if (theme === "light") {
    check("오류: 두 입력 모두 aria-invalid", (await page.locator('input[aria-invalid="true"]').count()) === 2)
    check("오류 문구 표시", (await page.getByRole("alert").innerText()).includes("모두 선택"))
  }

  // 3 고급 옵션 열림
  await page.getByRole("button", { name: "고급 옵션" }).click()
  await page.waitForTimeout(300)
  await shot("3_advanced")
  await page.getByRole("button", { name: "고급 옵션" }).click()

  // 4 백업 중 (진행바 + Skeleton)
  await page.locator("#source").fill("/home/user/프로젝트")
  await page.locator("#target").fill("/home/user/백업")
  if (theme === "light") check("입력을 고치면 오류가 사라짐", (await page.locator('input[aria-invalid="true"]').count()) === 0)
  await start.click()
  await page.waitForTimeout(600)
  await shot("4_running")
  if (theme === "light") {
    check("백업 중 BusyBar 활성", (await page.getByRole("progressbar").getAttribute("aria-busy")) === "true")
    check("실행 중 입력 잠김", await page.locator("#source").isDisabled())
  }

  // 5 완료
  await page.waitForTimeout(2200)
  await shot("5_done")
  if (theme === "light") check("완료 로그에 이모지 없음", !/[\u{1F300}-\u{1FAFF}✅]/u.test(await page.getByRole("log").innerText()))

  // 6 중지(취소)
  await page.getByRole("button", { name: "중지" }).click()
  await page.waitForTimeout(500)
  await shot("6_stopped")
  await context.close()
}
await browser.close()
const failed = checks.filter((ok) => !ok).length
console.log(`${checks.length - failed}/${checks.length} checks passed`)
process.exit(failed ? 1 : 0)
