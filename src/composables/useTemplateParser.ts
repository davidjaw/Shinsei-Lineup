import { useData } from './useData'

export interface Segment {
  type: 'text' | 'status' | 'dmg' | 'scale' | 'stat'
  value?: string
  data?: any
}

export const PLACEHOLDER_REGEX = /\{(\w+):([^\}]+)\}/g
export const RANGE_REGEX = /(\d+(?:\.\d+)?%?)\s*(?:->|to|→)\s*(\d+(?:\.\d+)?%?)/g

/**
 * 模板解析器 - 將技能描述中的 {type:content} 模板轉換為可渲染的segments
 * 支持的模板：{status:id}, {dmg:type}, {scale:stat}, {stat:id}, {var:name}
 */
export function useTemplateParser() {
  const { statuses } = useData()

  const formatAsPercent = (n: number): string => {
    const pct = Math.round(n * 1000) / 10
    return pct % 1 === 0 ? `${pct.toFixed(0)}%` : `${pct}%`
  }

  const formatVarValue = (v: any, isMax: boolean, asPercent: boolean = false): string => {
    if (typeof v === 'number') {
      // Static number — if followed by '%' in template or value < 1, format as percent
      if (asPercent || (v > 0 && v < 1)) return formatAsPercent(v)
      return String(v)
    }
    if (v && typeof v === 'object' && 'base' in v && 'max' in v) {
      const val = isMax ? v.max : v.base
      if (v.type === 'flat') return String(val)
      return typeof val === 'number' ? formatAsPercent(val) : String(val)
    }
    return String(v)
  }

  const parseText = (inputText: string, isMaxLevel: boolean = false, vars?: Record<string, any>): Segment[] => {
    if (!inputText) return []

    // 1. Level toggling (處理範圍值如 64% → 128%)
    let text = inputText.replace(RANGE_REGEX, (match, min, max) => {
      return isMaxLevel ? max : min
    })

    // 2. Parse placeholders
    const segments: Segment[] = []
    let lastIndex = 0
    let match

    // Reset regex lastIndex
    PLACEHOLDER_REGEX.lastIndex = 0

    while ((match = PLACEHOLDER_REGEX.exec(text)) !== null) {
      if (match.index > lastIndex) {
        segments.push({ type: 'text', value: text.substring(lastIndex, match.index) })
      }

      const type = match[1]
      const content = match[2]

      if (type === 'status') {
        const statusData = statuses.value[content]
        segments.push({
          type: 'status',
          data: statusData || { name: content, description: '未知狀態' }
        })
      } else if (type === 'dmg') {
        const dmgData = statuses.value._damage_types?.[content]
        segments.push({
          type: 'dmg',
          data: dmgData || { name: content }
        })
      } else if (type === 'scale') {
        const parts = content.split(':')
        const statKey = parts[0]
        const value = parts[1] || null
        const statData = statuses.value._stats?.[statKey]

        segments.push({
          type: 'scale',
          data: {
            value: value,
            statInfo: statData?.name || statKey
          }
        })
      } else if (type === 'stat') {
        // Direct stat reference
        const statData = statuses.value._stats?.[content]
        segments.push({
          type: 'stat',
          data: statData || { name: content }
        })
      } else if (type === 'var') {
        if (vars && vars[content] !== undefined) {
          const v = vars[content]
          // Check if next char is '%' — if so, LLM expects raw*100 display, consume the '%'
          const nextCharIdx = PLACEHOLDER_REGEX.lastIndex
          const hasTrailingPercent = text[nextCharIdx] === '%'
          if (hasTrailingPercent) {
            PLACEHOLDER_REGEX.lastIndex = nextCharIdx + 1
          }
          segments.push({ type: 'text', value: formatVarValue(v, isMaxLevel, hasTrailingPercent) })
        } else {
          segments.push({ type: 'text', value: content })
        }
      } else {
        segments.push({ type: 'text', value: match[0] })
      }

      lastIndex = PLACEHOLDER_REGEX.lastIndex
    }

    if (lastIndex < text.length) {
      segments.push({ type: 'text', value: text.substring(lastIndex) })
    }

    return segments
  }

  /**
   * 將text轉換為純文字，去除所有HTML標籤（用於brief description）
   */
  const parseTextToPlain = (inputText: string, isMaxLevel: boolean = false, vars?: Record<string, any>): string => {
    const segments = parseText(inputText, isMaxLevel, vars)
    return segments
      .map(seg => {
        if (seg.type === 'text') return seg.value
        if (seg.type === 'status') return seg.data?.name || ''
        if (seg.type === 'dmg') return seg.data?.name || ''
        if (seg.type === 'scale') {
          let result = ''
          if (seg.data?.value) result += seg.data.value
          if (seg.data?.statInfo) result += (result ? '受' : '') + seg.data.statInfo + '影響'
          return result
        }
        if (seg.type === 'stat') return seg.data?.name || ''
        return ''
      })
      .join('')
  }

  return {
    parseText,
    parseTextToPlain,
    PLACEHOLDER_REGEX,
    RANGE_REGEX
  }
}
