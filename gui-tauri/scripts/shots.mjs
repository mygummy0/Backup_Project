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
{
  const context = await browser.newContext({ viewport: { width: 640, height: 650 } })
  const page = await context.newPage()
  await page.goto(`${base}/?theme=light`)
  await page.getByRole("button", { name: "시작" }).click()
  await page.waitForTimeout(400)
  check("마우스 클릭 뒤 버튼에 외곽선/후광 없음", await page.getByRole("button", { name: "시작" }).evaluate((el) => {
    const s = getComputedStyle(el)
    return s.outlineStyle === "none" && s.boxShadow === "none"
  }))
  await context.close()
}
for (const theme of ["light", "dark"]) {
  const context = await browser.newContext({ viewport: { width: 640, height: 900 }, locale: "ko-KR" })
  const page = await context.newPage()
  await page.goto(`${base}/?theme=${theme}`)
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  const shot = (name) => page.screenshot({ path: `${out}/${theme}_${name}.png` })
  const start = page.getByRole("button", { name: "시작" })

  // 1 초기
  await shot("1_initial")
  if (theme === "light") {
    const fit = await page.evaluate(() => {
      const cards = [...document.querySelectorAll("[data-slot=card]")].map((c) => c.getBoundingClientRect())
      return {
        count: cards.length,
        top: Math.round(cards[0].top),
        left: Math.round(Math.min(...cards.map((c) => c.left))),
        right: Math.round(Math.max(...cards.map((c) => c.right))),
        bottom: Math.round(cards[cards.length - 1].bottom),
        width: window.innerWidth,
        height: window.innerHeight,
        scrolls: document.querySelector("main").scrollHeight > document.querySelector("main").clientHeight,
        gearInsideCard: !!document.querySelector("[data-slot=card] button[aria-label='설정']"),
      }
    })
    check("카드 3개", fit.count === 3)
    check("바깥 여백 0: 카드가 창 위·왼쪽·오른쪽·아래에 딱 붙음", fit.top === 0 && fit.left === 0 && fit.right === fit.width && fit.bottom === fit.height, JSON.stringify(fit))
    check("기본 창 크기(640x650)에서 스크롤 없음", !fit.scrolls)
    check("설정 버튼이 첫 카드 안에 있음", fit.gearInsideCard)
  }

  // 접근성/상태 검증 (라이트에서 한 번)
  if (theme === "light") {
    const order = []
    await page.locator("body").click({ position: { x: 2, y: 2 } })
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Tab")
      order.push(await page.evaluate(() => {
        const el = document.activeElement
        return el.id || el.getAttribute("aria-label") || el.getAttribute("role") || el.textContent?.trim() || el.tagName
      }))
    }
    console.log("tab order:", order.join(" > "))
    check("Tab 순서 = 화면 순서", order.join(",") === "설정,source,선택,target,선택,시작")
    check("키보드 포커스: 2px 외곽선, 후광 없음", await start.evaluate((el) => {
      const s = getComputedStyle(el)
      return s.outlineStyle !== "none" && s.outlineWidth === "2px" && s.boxShadow === "none"
    }))
    const style = (sel, prop) => page.locator(sel).first().evaluate((el, p) => getComputedStyle(el)[p], prop)
    check("Server Mono 로딩", await page.evaluate(async () => { await document.fonts.load('14px ServerMono', "0"); return document.fonts.check('14px ServerMono', "0") }))
    check("Pretendard(한글) 로딩", await page.evaluate(async () => { await document.fonts.load('14px "Pretendard Variable"', "백"); return document.fonts.check('14px "Pretendard Variable"', "백") }))
    check("화면에 '자동' 문구 없음", !(await page.locator("body").innerText()).includes("자동"))
    check("폴더 입력에 플레이스홀더 없음", (await page.locator("#source").getAttribute("placeholder")) === null)
    check("본문 폰트 = Server Mono (한글은 Pretendard로 대체)", (await style("body", "fontFamily")).startsWith("ServerMono"))
    check("가짜 굵기 없음 (font-synthesis: none)", (await style("body", "fontSynthesis")) === "none")
    check("자간 -0.02em (14px → -0.28px)", (await style("body", "letterSpacing")) === "-0.28px")
    check("행간 1.55 (14px → 21.7px)", (await style("body", "lineHeight")) === "21.7px")
    check("제목 굵기 400 (단일 굵기)", (await style("h1", "fontWeight")) === "400")
    check("타이머 굵기 400 (크기로 위계)", (await style("[class*=text-4xl]", "fontWeight")) === "400")
    check("카드 그림자 없음", (await style("[data-slot=card]", "boxShadow")) === "none")
    check("전환 시간 300ms", await start.evaluate((el) => getComputedStyle(el).transitionDuration.includes("0.3s")))

    await page.mouse.move(0, 0)
    await start.hover()
    await page.waitForTimeout(350)
    check("hover = slate-800", (await start.evaluate((el) => getComputedStyle(el).backgroundColor)) === rgb("#1E293B"))
    await page.mouse.down()
    await page.waitForTimeout(350)
    check("active = slate-950", (await start.evaluate((el) => getComputedStyle(el).backgroundColor)) === rgb("#020617"))
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

  // 3 설정 창: 일반 탭 -> 고급 옵션 탭
  const gear = page.getByRole("button", { name: "설정" })
  await gear.click()
  await page.waitForTimeout(400)
  await shot("3_settings_general")
  if (theme === "light") {
    check("설정 창이 열림", await page.getByRole("dialog").isVisible())
    check("일반 탭에 주기·보관", (await page.locator("#interval").isVisible()) && (await page.locator("#keep").isVisible()))
  }
  await page.getByRole("tab", { name: "고급 옵션" }).click()
  await page.waitForTimeout(400)
  await shot("3b_settings_advanced")
  if (theme === "light") {
    check("고급 옵션 탭 선택됨", (await page.getByRole("tab", { name: "고급 옵션" }).getAttribute("aria-selected")) === "true")
    check("고급 옵션: 증분·검증·제외", (await page.locator("#incremental").isVisible()) && (await page.locator("#verify").isVisible()) && (await page.locator("#excludes").isVisible()))
    await page.locator("#incremental").click()
    check("증분 스위치 켜짐", (await page.locator("#incremental").getAttribute("aria-checked")) === "true")
  }
  await page.keyboard.press("Escape")
  await page.waitForTimeout(400)
  if (theme === "light") {
    await page.keyboard.press("Control+,")
    await page.waitForTimeout(400)
    check("Ctrl+, 로 설정 창 열림", await page.getByRole("dialog").isVisible())
    await page.keyboard.press("Escape")
    await page.waitForTimeout(400)
    check("Esc로 닫히고 포커스가 설정 버튼으로 복귀", (await page.getByRole("dialog").count()) === 0 && (await page.evaluate(() => document.activeElement?.getAttribute("aria-label"))) === "설정")
  }

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
