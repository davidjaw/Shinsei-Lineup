<template>
  <el-dialog
    v-model="visible"
    :fullscreen="isMobile"
    :width="isMobile ? '100%' : '560px'"
    :show-close="true"
    align-center
    class="changelog-dialog"
    append-to-body
  >
    <template #header>
      <div class="flex items-center gap-3 pr-8">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-md flex-shrink-0">
          <el-icon :size="20" class="text-white"><Bell /></el-icon>
        </div>
        <div class="min-w-0">
          <div class="text-base sm:text-lg font-bold text-gray-800 leading-tight">
            更新紀錄
          </div>
          <div class="text-xs text-gray-500 mt-0.5">
            最新 v{{ latestVersion }}
          </div>
        </div>
      </div>
    </template>

    <div class="changelog-body">
      <div
        v-for="(v, idx) in CHANGELOG"
        :key="v.version"
        class="changelog-version"
      >
        <div class="flex items-baseline gap-2 mb-2">
          <span class="text-base font-bold text-gray-800">v{{ v.version }}</span>
          <span class="text-xs text-gray-400">{{ v.date }}</span>
          <span
            v-if="idx === 0"
            class="ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 border border-emerald-200"
          >
            最新
          </span>
        </div>

        <ul class="space-y-1.5 pl-1 mb-4">
          <li
            v-for="(e, i) in v.entries"
            :key="i"
            class="flex gap-2 items-start text-sm text-gray-700 leading-relaxed"
          >
            <span
              v-if="e.tag"
              class="text-[10px] font-semibold px-1.5 py-0.5 rounded border flex-shrink-0 mt-0.5"
              :class="TAG_COLORS[e.tag]"
            >
              {{ TAG_LABELS[e.tag] }}
            </span>
            <span v-else class="text-gray-400 mt-0.5">·</span>
            <span class="flex-1 min-w-0">{{ e.text }}</span>
          </li>
        </ul>

        <div v-if="idx < CHANGELOG.length - 1" class="border-b border-gray-100 mb-4"></div>
      </div>
    </div>

    <template #footer>
      <el-button type="primary" size="default" @click="visible = false" class="!w-full sm:!w-auto sm:!ml-auto">
        知道了
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Bell } from '@element-plus/icons-vue'
import {
  CHANGELOG, LATEST_VERSION, TAG_LABELS, TAG_COLORS,
} from '../../constants/changelog'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const latestVersion = LATEST_VERSION

const isMobile = ref(false)
const mq = window.matchMedia('(max-width: 767px)')
const updateMobile = () => { isMobile.value = mq.matches }
onMounted(() => {
  updateMobile()
  mq.addEventListener('change', updateMobile)
})
onUnmounted(() => mq.removeEventListener('change', updateMobile))
</script>

<style scoped>
.changelog-body {
  max-height: calc(70vh - 160px);
  overflow-y: auto;
  padding-right: 4px;
}
@media (max-width: 767px) {
  .changelog-body {
    max-height: none;
  }
}
:deep(.changelog-dialog .el-dialog__header) {
  margin-right: 0;
  padding-right: 16px;
}
.changelog-version + .changelog-version {
  margin-top: 4px;
}
</style>
