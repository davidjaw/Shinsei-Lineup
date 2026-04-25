<template>
  <!-- Empty state: full-width button spanning 4 color-coded stripes -->
  <button
    v-if="!modelValue.direction"
    type="button"
    class="bingxue-empty-btn relative w-full flex items-stretch rounded border border-dashed border-gray-300 bg-white hover:border-indigo-400 hover:bg-indigo-50 transition-all overflow-hidden group"
    @click="openDialog"
  >
    <div class="flex-1 h-6 md:h-7 bg-red-400/70 group-hover:bg-red-500"></div>
    <div class="flex-1 h-6 md:h-7 bg-amber-500/70 group-hover:bg-amber-600"></div>
    <div class="flex-1 h-6 md:h-7 bg-purple-400/70 group-hover:bg-purple-500"></div>
    <div class="flex-1 h-6 md:h-7 bg-emerald-400/70 group-hover:bg-emerald-500"></div>
    <div class="absolute inset-0 pointer-events-none flex items-center justify-center font-bold text-white text-[10px] md:text-xs tracking-wider" style="text-shadow: 0 1px 2px rgba(0,0,0,0.5)">
      兵學 配置
    </div>
  </button>

  <!-- Filled state: major name (full width) + minor chips. Wrapped in popover
       so hover reveals the full major + per-minor descriptions at the selected
       level. Click still opens the selection dialog. -->
  <el-popover
    v-else
    placement="bottom"
    :width="340"
    trigger="hover"
    :show-after="200"
    :offset="8"
  >
    <template #reference>
      <div
        class="w-full rounded border overflow-hidden cursor-pointer transition-all"
        :class="borderClass"
        @click="openDialog"
      >
        <!-- Major name header (100% width, direction-colored) -->
        <div
          class="flex items-center justify-between px-1.5 md:px-2 py-1 text-white font-bold text-[10px] md:text-sm"
          :class="headerClass"
        >
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="text-[9px] md:text-[11px] opacity-80 flex-shrink-0">{{ modelValue.direction }}</span>
            <span class="truncate">{{ majorDisplay }}</span>
          </div>
          <button
            type="button"
            class="flex-shrink-0 opacity-70 hover:opacity-100 leading-none"
            @click.stop="clearSelection"
            title="清除兵學"
          >
            <el-icon :size="12"><Close /></el-icon>
          </button>
        </div>

        <!-- Minor chips: w-1/3 each, wrap. Only show actually-selected minors. -->
        <div
          v-if="modelValue.minors.length"
          class="flex flex-wrap p-0.5 md:p-1 gap-0.5 md:gap-1 bg-white"
        >
          <div
            v-for="(minor, idx) in modelValue.minors"
            :key="minor.name + idx"
            class="w-[calc(33.333%-2px)] md:w-[calc(33.333%-4px)] text-center rounded border text-[8px] md:text-[11px] px-1 py-0.5 truncate"
            :class="chipClass"
          >
            {{ optionName(minor.name) }} {{ roman(minor.level) }}
          </div>
        </div>
      </div>
    </template>

    <!-- Popover content: major + each minor with full description -->
    <div class="space-y-2.5 text-gray-700">
      <!-- Major block -->
      <div v-if="modelValue.major">
        <div class="flex items-center gap-1.5 mb-1">
          <span
            class="text-[10px] font-extrabold px-1.5 py-0.5 rounded"
            :class="colorBadgeClassFor(modelValue.direction!)"
          >{{ modelValue.direction }} · 主</span>
          <span class="font-bold text-sm" :class="colorTextClassFor(modelValue.direction!)">
            {{ optionName(modelValue.major) }}
          </span>
        </div>
        <SkillDescription
          :description="optionDescription(modelValue.major)"
          :vars="optionVars(modelValue.major)"
          class="!text-xs !leading-relaxed pl-1"
        />
      </div>

      <!-- Minor list -->
      <div v-if="modelValue.minors.length" class="border-t pt-2 space-y-2">
        <div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider">副戰法 · {{ modelValue.minors.length }} 項</div>
        <div
          v-for="(minor, idx) in modelValue.minors"
          :key="minor.name + idx"
          class="space-y-0.5"
        >
          <div class="flex items-center gap-1.5">
            <span class="font-bold text-xs">{{ optionName(minor.name) }}</span>
            <span
              class="text-[9px] font-extrabold px-1 rounded"
              :class="colorBadgeClassFor(modelValue.direction!)"
            >Lv {{ roman(minor.level) }}</span>
          </div>
          <SkillDescription
            :description="optionDescription(minor.name)"
            :vars="optionVars(minor.name)"
            :is-max-level="minor.level === 2"
            class="!text-[11px] !leading-snug pl-1"
          />
        </div>
      </div>
    </div>
  </el-popover>

  <!-- Selection dialog -->
  <el-dialog
    v-model="dialogVisible"
    :title="`兵學配置 — ${hero?.name || ''}`"
    width="820px"
    append-to-body
    align-center
  >
    <div v-if="!hero?.bingxue" class="text-center text-gray-500 text-base py-10">
      此武將尚未開放兵學系統
    </div>
    <template v-else>
      <!-- Direction tabs -->
      <el-tabs v-model="draftDirection" class="bingxue-tabs" stretch>
        <el-tab-pane
          v-for="dir in BINGXUE_DIRECTIONS"
          :key="dir"
          :name="dir"
        >
          <template #label>
            <span :class="colorTextClassFor(dir)">{{ dir }}</span>
          </template>
          <div v-if="!hero?.bingxue?.[dir]" class="text-base text-gray-400 py-6 text-center">
            此方向未開放
          </div>
          <template v-else>
            <!-- Major selection -->
            <div class="mb-4">
              <div class="text-sm font-bold mb-2 flex items-center justify-between">
                <span :class="colorTextClassFor(dir)">主戰法（擇一）</span>
                <span class="text-xs text-gray-400">1 點</span>
              </div>
              <div class="grid grid-cols-3 gap-2">
                <div
                  v-for="jp in hero.bingxue[dir].major"
                  :key="jp"
                  class="relative rounded border p-2.5 cursor-pointer transition-all"
                  :class="draftMajor === jp
                    ? colorCardActiveFor(dir)
                    : 'border-gray-200 hover:border-gray-400 bg-gray-50'"
                  @click="selectMajor(jp)"
                >
                  <div class="font-bold text-sm mb-1 truncate">{{ optionName(jp) }}</div>
                  <SkillDescription
                    :description="optionDescription(jp)"
                    :vars="optionVars(jp)"
                    class="!text-xs !leading-relaxed"
                  />
                </div>
              </div>
            </div>

            <!-- Minor selection: click the card to level up (none → I → II).
                 The × button in the corner resets back to unselected. -->
            <div>
              <div class="text-sm font-bold mb-2 flex items-center justify-between">
                <span :class="colorTextClassFor(dir)">副戰法（點卡片升級，總共 5 點）</span>
                <span class="text-xs" :class="pointsOverflow ? 'text-red-500' : 'text-gray-400'">
                  {{ draftPoints }} / {{ MAX_POINTS }} 點
                </span>
              </div>
              <div class="grid grid-cols-3 gap-2">
                <div
                  v-for="jp in hero.bingxue[dir].minor"
                  :key="jp"
                  class="relative rounded border p-2.5 transition-all select-none"
                  :class="minorLevel(jp) > 0
                    ? colorCardActiveFor(dir) + ' cursor-pointer'
                    : canAdvanceMinor(jp)
                      ? 'border-gray-200 hover:border-gray-400 bg-gray-50 cursor-pointer'
                      : 'border-gray-100 bg-gray-50 opacity-50 cursor-not-allowed'"
                  @click="advanceMinor(jp)"
                >
                  <!-- Per-minor reset button (visible when selected) -->
                  <button
                    v-if="minorLevel(jp) > 0"
                    type="button"
                    class="absolute top-1 right-1 w-5 h-5 flex items-center justify-center rounded-full bg-white/80 hover:bg-white text-gray-500 hover:text-red-500 transition-colors"
                    title="取消此項"
                    @click.stop="resetMinor(jp)"
                  >
                    <el-icon :size="12"><Close /></el-icon>
                  </button>

                  <div class="flex items-center gap-1.5 mb-1.5 pr-6">
                    <div class="font-bold text-sm truncate">{{ optionName(jp) }}</div>
                    <span
                      v-if="minorLevel(jp) > 0"
                      class="text-[10px] font-extrabold px-1.5 py-0.5 rounded flex-shrink-0"
                      :class="colorBadgeClassFor(dir)"
                    >Lv {{ roman(minorLevel(jp)) }}</span>
                    <span
                      v-else-if="canAdvanceMinor(jp)"
                      class="text-[10px] text-gray-400 italic flex-shrink-0"
                    >點擊選取</span>
                  </div>
                  <SkillDescription
                    :description="optionDescription(jp)"
                    :vars="optionVars(jp)"
                    :is-max-level="minorLevel(jp) === 2"
                    class="!text-xs !leading-relaxed"
                  />
                  <div
                    v-if="minorLevel(jp) === 1 && canAdvanceMinor(jp)"
                    class="mt-1.5 text-[10px] italic text-gray-500"
                  >
                    再點一次 → Lv II
                  </div>
                </div>
              </div>
            </div>
          </template>
        </el-tab-pane>
      </el-tabs>
    </template>

    <template #footer>
      <div class="flex items-center justify-between">
        <el-button v-if="modelValue.direction" link type="danger" @click="resetAll">清除</el-button>
        <div v-else></div>
        <div class="flex gap-2">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :disabled="!canApply" @click="applyDraft">套用</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import SkillDescription from './SkillDescription.vue'
import { useData, BINGXUE_DIRECTIONS, type Hero, type BingxueDirection } from '../composables/useData'
import type { BingxueActive, BingxueMinor } from '../composables/useLineups'

const props = defineProps<{
  hero: Hero | null
  modelValue: BingxueActive
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: BingxueActive): void
}>()

const MAX_MINORS = 5     // display cap (also 5 slots max even if you only spent 3 pts)
const MAX_POINTS = 5     // minor skill-point budget

const { bingxue: bingxueCatalog } = useData()

// Dialog state (draft is a local copy; applied on save)
const dialogVisible = ref(false)
const draftDirection = ref<BingxueDirection>('武略')
const draftMajor = ref<string | null>(null)
const draftMinors = ref<BingxueMinor[]>([])

const cloneMinors = (src: BingxueMinor[]): BingxueMinor[] => src.map(m => ({ ...m }))

const openDialog = () => {
  const startDir = props.modelValue.direction
    ?? BINGXUE_DIRECTIONS.find(d => props.hero?.bingxue?.[d])
    ?? '武略'
  draftDirection.value = startDir
  draftMajor.value = props.modelValue.direction === startDir ? props.modelValue.major : null
  draftMinors.value = props.modelValue.direction === startDir ? cloneMinors(props.modelValue.minors) : []
  dialogVisible.value = true
}

watch(draftDirection, (newDir, oldDir) => {
  if (newDir === oldDir) return
  if (newDir === props.modelValue.direction) {
    draftMajor.value = props.modelValue.major
    draftMinors.value = cloneMinors(props.modelValue.minors)
  } else {
    draftMajor.value = null
    draftMinors.value = []
  }
})

const selectMajor = (jp: string) => {
  draftMajor.value = draftMajor.value === jp ? null : jp
}

const minorLevel = (jp: string): 0 | 1 | 2 => {
  const m = draftMinors.value.find(m => m.name === jp)
  return (m?.level ?? 0) as 0 | 1 | 2
}

const draftPoints = computed(() =>
  draftMinors.value.reduce((sum, m) => sum + m.level, 0)
)
const pointsOverflow = computed(() => draftPoints.value > MAX_POINTS)

// Click card: advance level (0 → 1 → 2). Stops at Lv 2; use resetMinor to clear.
// Advance disabled if adding the next point would exceed budget or slot cap.
const canAdvanceMinor = (jp: string): boolean => {
  const cur = minorLevel(jp)
  if (cur === 2) return false                   // already maxed
  const slotDelta = cur === 0 ? 1 : 0
  if (draftMinors.value.length + slotDelta > MAX_MINORS) return false
  if (draftPoints.value + 1 > MAX_POINTS) return false
  return true
}

const advanceMinor = (jp: string) => {
  if (!canAdvanceMinor(jp)) return
  const i = draftMinors.value.findIndex(m => m.name === jp)
  if (i < 0) {
    draftMinors.value.push({ name: jp, level: 1 })
  } else {
    draftMinors.value[i] = { ...draftMinors.value[i], level: 2 }
  }
}

const resetMinor = (jp: string) => {
  const i = draftMinors.value.findIndex(m => m.name === jp)
  if (i >= 0) draftMinors.value.splice(i, 1)
}

const canApply = computed(() =>
  !!draftMajor.value && !pointsOverflow.value
)

const applyDraft = () => {
  emit('update:modelValue', {
    direction: draftDirection.value,
    major: draftMajor.value,
    minors: cloneMinors(draftMinors.value),
  })
  dialogVisible.value = false
}

const resetAll = () => {
  emit('update:modelValue', { direction: null, major: null, minors: [] })
  dialogVisible.value = false
}

const clearSelection = () => {
  emit('update:modelValue', { direction: null, major: null, minors: [] })
}

// Display helpers
const lookup = (jp: string) => bingxueCatalog.value[jp]
const optionName = (jp: string) => lookup(jp)?.name ?? jp
const optionDescription = (jp: string) => lookup(jp)?.description ?? ''
const optionVars = (jp: string) => lookup(jp)?.vars ?? {}
const majorDisplay = computed(() => (props.modelValue.major ? optionName(props.modelValue.major) : '未選擇主戰法'))

// Roman numerals — only need 1 and 2 for now (extends trivially if a 5th level ever arrives)
const roman = (n: number): string => ['', 'I', 'II', 'III', 'IV', 'V'][n] ?? String(n)

// Color styling per direction (matches game UI colors from user)
const headerClass = computed(() => {
  const d = props.modelValue.direction
  return d === '武略' ? 'bg-red-500'
    : d === '陣立' ? 'bg-amber-600'
    : d === '機略' ? 'bg-purple-500'
    : d === '臨戰' ? 'bg-emerald-500'
    : 'bg-gray-400'
})
const borderClass = computed(() => {
  const d = props.modelValue.direction
  return d === '武略' ? 'border-red-300'
    : d === '陣立' ? 'border-amber-300'
    : d === '機略' ? 'border-purple-300'
    : d === '臨戰' ? 'border-emerald-300'
    : 'border-gray-200'
})
const chipClass = computed(() => {
  const d = props.modelValue.direction
  return d === '武略' ? 'bg-red-50 border-red-200 text-red-700'
    : d === '陣立' ? 'bg-amber-50 border-amber-200 text-amber-700'
    : d === '機略' ? 'bg-purple-50 border-purple-200 text-purple-700'
    : d === '臨戰' ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
    : 'bg-gray-50 border-gray-200 text-gray-700'
})

const colorTextClassFor = (d: BingxueDirection) => {
  return d === '武略' ? 'text-red-600'
    : d === '陣立' ? 'text-amber-700'
    : d === '機略' ? 'text-purple-600'
    : d === '臨戰' ? 'text-emerald-600'
    : 'text-gray-600'
}
const colorCardActiveFor = (d: BingxueDirection) => {
  return d === '武略' ? 'border-red-400 bg-red-50 ring-1 ring-red-300'
    : d === '陣立' ? 'border-amber-500 bg-amber-50 ring-1 ring-amber-300'
    : d === '機略' ? 'border-purple-400 bg-purple-50 ring-1 ring-purple-300'
    : d === '臨戰' ? 'border-emerald-400 bg-emerald-50 ring-1 ring-emerald-300'
    : 'border-gray-400 bg-gray-50'
}
const colorBadgeClassFor = (d: BingxueDirection) => {
  return d === '武略' ? 'bg-red-500 text-white'
    : d === '陣立' ? 'bg-amber-600 text-white'
    : d === '機略' ? 'bg-purple-500 text-white'
    : d === '臨戰' ? 'bg-emerald-500 text-white'
    : 'bg-gray-400 text-white'
}

</script>

<style scoped>
:deep(.bingxue-tabs .el-tabs__item) {
  font-weight: 700;
  font-size: 15px;
  height: 42px;
  line-height: 42px;
}
:deep(.bingxue-tabs .el-tabs__nav-wrap::after) {
  height: 1px;
}
</style>
