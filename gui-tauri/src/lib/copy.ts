/** 화면에 보이는 모든 문구. 문구를 바꾸려면 이 파일만 고치면 된다. (이모지 금지) */
export const COPY = {
  /** 화면에는 보이지 않는다(스크린리더용 제목) */
  title: "백업",
  source: { label: "원본" },
  target: { label: "저장" },
  pick: "선택",
  interval: "주기",
  keep: "보관",
  settings: "설정",
  settingsHint: "백업 옵션", // 스크린리더용
  tabs: { general: "일반", advanced: "고급 옵션" },
  incremental: { label: "증분" },
  verify: { label: "검증" },
  excludes: { label: "제외", placeholder: "node_modules" },
  intervalOptions: [
    { label: "30초", seconds: 30 },
    { label: "1분", seconds: 60 },
    { label: "5분", seconds: 300 },
    { label: "10분", seconds: 600 },
    { label: "30분", seconds: 1800 },
    { label: "1시간", seconds: 3600 },
  ],
  defaultInterval: "5분",
  keepOptions: [
    { label: "무제한", count: 0 },
    { label: "최근 3개", count: 3 },
    { label: "최근 5개", count: 5 },
    { label: "최근 10개", count: 10 },
    { label: "최근 30개", count: 30 },
  ],
  defaultKeep: "무제한",
  nextBackup: "다음 백업까지", // 스크린리더용
  idleTimer: "--:--",
  start: "시작",
  stop: "중지",
  history: "기록", // 스크린리더용
  settingsHeading: "설정", // 스크린리더용
  runHeading: "실행", // 스크린리더용
  progressLabel: "백업 진행",
  log: {
    started: (interval: string) => `시작 ${interval}`,
    stopped: "중지",
    skippedBusy: "진행 중, 건너뜀",
    error: (detail: string) => `오류 ${detail}`,
  },
} as const
