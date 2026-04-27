// Changelog data — append new versions to the top.
// LATEST_VERSION drives the auto-open behavior of WhatsNewDialog: when this
// constant changes, every user sees the dialog once on their next visit.

export type ChangelogTag = 'feat' | 'fix' | 'ui' | 'data' | 'misc'

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
  misc: '其他',
}

export const TAG_COLORS: Record<ChangelogTag, string> = {
  feat: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  fix: 'bg-rose-50 text-rose-700 border-rose-200',
  ui: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  data: 'bg-amber-50 text-amber-700 border-amber-200',
  misc: 'bg-gray-50 text-gray-600 border-gray-200',
}

export const CHANGELOG: ChangelogVersion[] = [
  {
    version: '0.2.1',
    date: '2026-04-27',
    entries: [
      { tag: 'fix', text: '登入更穩定：改善 token 自動續約邏輯，網路抖動或同時觸發多個操作時不再被誤登出' },
      { tag: 'fix', text: '登入逾時不再重新整理頁面 — 自動切回未登入狀態並保留編輯中的隊伍與庫存，以提示告知重新登入即可' },
    ],
  },
  {
    version: '0.2.0',
    date: '2026-04-26',
    entries: [
      { tag: 'feat', text: '角色配置：登入後可儲存多套庫存為命名配置（例：主帳 / 小號 / 幫朋友配將），隨時切換。下次登入自動載入預設配置' },
      { tag: 'feat', text: '從分享連結匯入：他人的「僅分享庫存」連結可直接貼進「管理角色配置」，存成你的新配置' },
      { tag: 'feat', text: '庫存編輯新增「全選 / 取消全選」按鈕，作用範圍跟著目前的搜尋與篩選結果' },
      { tag: 'ui', text: '使用者選單顯示目前角色配置，並依用途重新分組（角色 / 分享 / 帳號）' },
      { tag: 'misc', text: '內部架構重構為未來功能鋪路；你看不出差別，那就代表它成功了' },
    ],
  },
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
