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
  /** 作者碎念 — informal author note rendered below the entries list. */
  note?: string
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
    version: '0.4.7',
    date: '2026-08-28',
    entries: [
      { tag: 'feat', text: '配將模擬在側欄分為「自由模式」與「庫存模式」；自由模式可使用全部武將／戰法' },
      { tag: 'feat', text: '自由模式與庫存模式現在各有獨立的編組／隊伍；切換模式不再共用同一套陣容' },
      { tag: 'feat', text: '匯入、分享、重置當前隊伍／編組只作用在目前模式；全部重置仍會清掉兩邊與庫存' },
      { tag: 'feat', text: '配將模擬新增截圖模式，方便一次截圖分享整個編組' },
    ],
    note: '兩邊的隊伍可以放同一名武將。庫存（擁有的武將／戰法）仍然共用。',
  },
  {
    version: '0.4.6',
    date: '2026-08-26',
    entries: [
      { tag: 'data', text: '新增本季事件戰法（誘敵深入、以逸待勞）' },
    ],
    note: '記得要把庫存模式關閉才能看到新增的事件戰法',
  },
  {
    version: '0.4.5',
    date: '2026-08-26',
    entries: [
      { tag: 'ui', text: '戰法圖示改為類型文字標（主／被／兵／陣／指），側欄版本號對齊更新紀錄' },
    ],
  },
  {
    version: '0.4.4',
    date: '2026-08-26',
    entries: [
      { tag: 'data', text: '新增 PK2 賽季武將（島津義久、龍造寺隆信、石川數正、吉岡妙林、相良義陽、種子島時堯）' },
    ],
  },
  {
    version: '0.4.3',
    date: '2026-07-11',
    entries: [
      { tag: 'data', text: '補充 PK 賽季武將兵學（伊達政宗、三好實休、佐竹義重、浦上宗景、大久保長安、藤林正保、長野業正 等）' },
      { tag: 'data', text: '重新爬取 S1～S3 武將屬性資料' },
    ],
  },
  {
    version: '0.4.2',
    date: '2026-06-24',
    entries: [
      { tag: 'fix', text: '修正切換隊伍或重新整理後，武將的突破與屬性數值會歸零的問題' },
      { tag: 'fix', text: '修正「我的提案」會誤顯示他人公開提案；並新增提案刪除功能' },
    ],
  },
  {
    version: '0.4.1',
    date: '2026-06-09',
    entries: [
      { tag: 'data', text: '新增本季事件戰法（出奇制勝、三河武士、越後先手組、追亡逐北）' },
    ],
    note: '記得要把庫存模式關閉才能看到新增的事件戰法',
  },
  {
    version: '0.4.0',
    date: '2026-05-18',
    entries: [
      { tag: 'ui', text: '整體版面大改版，各位都是我的白老鼠，有問題拜託反饋（電腦版找左下角建議與回報）' },
    ],
    note: '官方現在內建配將算不算官方逼死同人(X)',
  },
  {
    version: '0.3.3',
    date: '2026-05-12',
    entries: [
      { tag: 'feat', text: '抽卡紀錄移至左側欄成為一級功能，不再藏在使用者選單裡' },
      { tag: 'ui', text: '抽卡紀錄頁改用切換池下拉選單，新增、重命名、刪除改為就地操作，減少彈窗層數' },
      { tag: 'ui', text: '所有功能頁面改用統一頁首列：頁名與說明顯示於頂部，右側固定保留通知鈴鐺與使用者選單；內容區去除外框讓視覺更乾淨' },
    ],
  },
  {
    version: '0.3.2',
    date: '2026-05-09',
    entries: [
      { tag: 'data', text: '置換資料來源以對齊中文戰法／武將名稱與部分屬性（兵種、勢力、家族、Cost、稀有度）' },
      { tag: 'fix', text: '改名後的舊分享連結仍可透過別名自動配對到對應的戰法／武將' },
      { tag: 'ui', text: '左側隊伍欄不再可橫向捲動' },
    ],
  },
  {
    version: '0.3.1',
    date: '2026-05-03',
    entries: [
      { tag: 'feat', text: '隊伍數量從 5 隊擴充到 10 隊；現有隊伍與分享連結皆相容，多出的 6–10 隊預設為空白' },
      { tag: 'ui', text: 'Footer 連結文字改為「建議或回報」，除翻譯問題外也歡迎提出功能建議' },
      { tag: 'data', text: '修正以下武將名稱、屬性或兵學：立花誾千代（名稱修正、新增兵學）、本多正信（屬性）、柿崎景家／鈴木佐大夫／加藤嘉明／真田昌幸／阿松／安宅冬康／伊達輝宗／阿初／阿江（新增兵學）' },
    ],
  },
  {
    version: '0.3.0',
    date: '2026-04-30',
    entries: [
      { tag: 'feat', text: '抽卡紀錄：登入後從右上使用者選單 →「抽卡紀錄」開啟。可建立多個自訂池、設定池內 S 級武將、即時登錄每抽，自動算保底；標記某武將為稀有後，本池內所有同名武將會一起亮起並重置保底計數' },
      { tag: 'feat', text: '抽卡紀錄分享：分享按鈕產生唯讀連結，對方開啟可看到完整時間軸、Top 10 與保底統計，無需登入' },
    ],
  },
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
