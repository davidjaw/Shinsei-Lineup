// Changelog data — append new versions to the top.
// LATEST_VERSION drives the auto-open behavior of WhatsNewDialog: when this
// constant changes, every user sees the dialog once on their next visit.

export type ChangelogTag = 'feat' | 'fix' | 'ui' | 'data'

export interface ChangelogEntry {
  text: string
  tag?: ChangelogTag
}

export interface ChangelogVersion {
  version: string
  date: string
  entries: ChangelogEntry[]
}

export const TAG_LABELS: Record<ChangelogTag, string> = {
  feat: '新功能',
  fix: '修正',
  ui: '介面',
  data: '資料',
}

export const TAG_COLORS: Record<ChangelogTag, string> = {
  feat: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  fix: 'bg-rose-50 text-rose-700 border-rose-200',
  ui: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  data: 'bg-amber-50 text-amber-700 border-amber-200',
}

export const CHANGELOG: ChangelogVersion[] = [
  {
    version: '0.1.0',
    date: '2026-04-26',
    entries: [
      { tag: 'feat', text: '更新紀錄頁：點 header ?  圖示可隨時查看；新版本發布會自動提示一次' },
      { tag: 'feat', text: 'Google / GitHub 登入，登入後可命名分享、管理「我的分享」清單' },
      { tag: 'feat', text: '一鍵分享：產生短網址連結，可分享單隊、全部隊伍或庫存' },
    ],
  },
]

export const LATEST_VERSION = CHANGELOG[0].version
