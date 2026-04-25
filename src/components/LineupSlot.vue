<template>
  <div class="bg-white rounded-md shadow-sm border border-gray-200 p-0.5 md:p-2 flex flex-col gap-0.5 md:gap-2 h-full relative">
    <!-- Shared SVG defs for breakthrough star gradient -->
    <svg width="0" height="0" class="absolute pointer-events-none" aria-hidden="true">
      <defs>
        <linearGradient id="breakStarGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#fff7c2" />
          <stop offset="35%" stop-color="#fbbf24" />
          <stop offset="70%" stop-color="#f97316" />
          <stop offset="100%" stop-color="#b91c1c" />
        </linearGradient>
        <radialGradient id="breakStarGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#fde68a" stop-opacity="0.9" />
          <stop offset="100%" stop-color="#dc2626" stop-opacity="0" />
        </radialGradient>
      </defs>
    </svg>
    <!-- Role Header -->
    <div class="flex items-center justify-between border-b border-gray-100 pb-0.5 md:pb-2 px-1 md:px-0">
      <span class="font-bold text-gray-700 text-[10px] md:text-base">{{ title }}</span>
      <div class="flex items-center">
        <!-- Swap Button (Mobile Only) -->
        <el-button v-if="hero" link size="small"
          class="md:hidden !p-0 !h-auto mr-1"
          :class="isSwapSource ? 'text-indigo-500' : 'text-gray-400'"
          @click.stop="$emit('swap-click')"
        >
          <el-icon><Sort /></el-icon>
        </el-button>
        <!-- Info Button (Mobile Only) -->
        <el-button v-if="hero" link size="small" class="md:hidden !p-0 !h-auto mr-1" @click.stop="$emit('open-detail')">
           <el-icon class="text-indigo-400"><InfoFilled /></el-icon>
        </el-button>
        <el-button v-if="hero" type="danger" link size="small" class="!p-0 !h-auto" @click="removeHero">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- Hero Slot -->
    <div
      class="rounded border-2 border-dashed flex items-center justify-center cursor-pointer transition-all relative overflow-hidden group w-full aspect-[3/4] md:order-1"
      :class="isDragTarget
        ? 'border-indigo-400 bg-indigo-50 scale-[1.02] shadow-md shadow-indigo-200'
        : isSwapSource
          ? 'border-indigo-500 ring-2 ring-indigo-500 border-gray-200'
          : swapModeActive
            ? 'border-indigo-300 ring-2 ring-indigo-200'
            : 'border-gray-200 hover:border-indigo-300'"
      :draggable="!!hero"
      @click="$emit('open-hero-select')"
      @dragstart="handleHeroDragStart"
      @dragend="$emit('hero-drag-end')"
      @dragover.prevent
      @drop.prevent="handleHeroDropEvent"
    >
      <div v-if="isDragTarget" class="absolute inset-0 flex flex-col items-center justify-center z-10 bg-indigo-50/60 pointer-events-none">
        <el-icon class="text-indigo-400 text-xl md:text-3xl"><Sort /></el-icon>
        <span class="text-indigo-500 text-[8px] md:text-xs mt-1 font-medium">放置交換</span>
      </div>
      <HeroCard v-if="hero" :hero="hero" hide-name class="w-full h-full border-none shadow-none pointer-events-none" />
      <div v-else class="text-gray-400 flex flex-col items-center py-2 md:py-10">
        <el-icon :size="16" class="md:text-3xl"><Plus /></el-icon>
        <span class="text-[9px] md:text-xs mt-0.5">選擇</span>
      </div>
    </div>

    <!-- Hero Name + Breakthrough Stars (名字靠左，星星靠右) -->
    <div v-if="hero" class="flex items-center gap-1 px-1 md:px-2 mt-0.5 md:mt-1 md:order-1">
      <div
        class="flex-1 min-w-0 font-bold text-gray-800 truncate text-[10px] md:text-sm"
        :title="hero.name"
      >
        {{ hero.name }}
      </div>
      <!-- Desktop: inline 5 stars with hover-fill preview -->
      <div
        class="hidden md:flex items-center gap-0.5 flex-shrink-0"
        @mouseleave="hoverStar = 0"
      >
        <button
          v-for="n in maxBreakthrough"
          :key="n"
          type="button"
          class="breakthrough-star"
          :class="{ 'is-filled': n <= displayStarCount }"
          :title="breakthrough === n ? '再次點擊重置' : `設定為 ${n} 星突破`"
          @mouseenter="hoverStar = n"
          @click.stop="setBreakthrough(n)"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" class="break-star-svg">
            <path d="M12 2.5 L14.85 9.1 L22 9.77 L16.5 14.64 L18.18 21.52 L12 17.77 L5.82 21.52 L7.5 14.64 L2 9.77 L9.15 9.1 Z" />
          </svg>
        </button>
      </div>
      <!-- Mobile: single star + ×N badge, tap to open popover picker -->
      <el-popover
        v-if="!isDesktop"
        ref="popoverRef"
        placement="bottom-end"
        trigger="click"
        :width="220"
        popper-class="breakthrough-popover"
        @hide="hoverStar = 0"
      >
        <template #reference>
          <button
            type="button"
            class="breakthrough-star flex items-center gap-0.5 flex-shrink-0"
            :class="{ 'is-filled': breakthrough > 0 }"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" class="break-star-svg">
              <path d="M12 2.5 L14.85 9.1 L22 9.77 L16.5 14.64 L18.18 21.52 L12 17.77 L5.82 21.52 L7.5 14.64 L2 9.77 L9.15 9.1 Z" />
            </svg>
            <span v-if="breakthrough > 1" class="text-[9px] font-bold leading-none text-red-600">×{{ breakthrough }}</span>
          </button>
        </template>
        <div class="text-center text-[11px] font-bold text-gray-600 mb-1">突破次數</div>
        <div
          class="flex items-center justify-center gap-1 py-1"
          @mouseleave="hoverStar = 0"
        >
          <button
            v-for="n in maxBreakthrough"
            :key="n"
            type="button"
            class="breakthrough-star"
            :class="{ 'is-filled': n <= displayStarCount }"
            @mouseenter="hoverStar = n"
            @click.stop="onMobilePickStar(n)"
          >
            <svg viewBox="0 0 24 24" width="26" height="26" class="break-star-svg">
              <path d="M12 2.5 L14.85 9.1 L22 9.77 L16.5 14.64 L18.18 21.52 L12 17.77 L5.82 21.52 L7.5 14.64 L2 9.77 L9.15 9.1 Z" />
            </svg>
          </button>
        </div>
        <div class="text-center text-[10px] text-gray-400 mt-1">
          點擊當前星數可重置
        </div>
      </el-popover>
    </div>

    <!-- Stats & Traits Area (Only when hero exists) -->
    <div v-if="hero" class="relative mb-1 md:mb-2 md:mt-1 md:pt-2 md:border-t md:border-gray-200 z-10 flex items-center gap-1 md:gap-3 px-1 md:px-2 justify-between md:justify-start md:order-3">
      <!-- Radar Chart (Desktop Only) -->
      <el-popover
        placement="right"
        :width="200"
        trigger="hover"
      >
        <template #reference>
          <div 
            class="hidden md:block bg-white rounded-full p-0.5 md:p-1 shadow-md border border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors group flex-shrink-0"
            @click.stop="openStatsEditor"
          >
            <RadarChart :stats="stats" :base-stats="heroBaseStats" :size="72" />
          </div>
        </template>
        
        <!-- Popover Content -->
        <div class="space-y-2">
          <div class="text-xs font-bold text-gray-500 border-b pb-1 mb-1">屬性總覽 (基礎+自由加點)</div>
          <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div v-for="(label, key) in statLabels" :key="key" class="flex justify-between">
              <span class="text-gray-600">{{ label }}</span>
              <span>
                <span class="font-bold text-gray-800">{{ heroBaseStats[key] }}</span>
                <span v-if="statBonus[key] > 0" class="text-green-600 ml-0.5">+{{ statBonus[key] }}</span>
                <span v-else-if="statBonus[key] < 0" class="text-red-500 ml-0.5">{{ statBonus[key] }}</span>
              </span>
            </div>
          </div>
          <div class="text-[10px] text-gray-400 mt-1">剩餘自由點: {{ freePointsRemaining }}</div>
          <div class="text-[10px] text-indigo-500 text-right italic">
            <el-icon class="align-middle mr-0.5"><Edit /></el-icon>點擊圖表調整
          </div>
        </div>
      </el-popover>

      <!-- Traits List (Right) -->
      <div class="flex-1 flex flex-col gap-0.5 md:gap-1 min-w-0">
        <span class="hidden md:block text-[10px] font-bold text-gray-500 ml-1">特性:</span>
        <div class="grid grid-cols-2 md:grid-cols-2 gap-0.5 md:gap-1.5 w-full">
          <el-tooltip
            v-for="(trait, idx) in localTraits" 
            :key="idx"
            placement="top"
            :show-after="300"
          >
            <template #content>
              <div class="max-w-[200px]">
                <div class="font-bold mb-1">{{ trait.name }}</div>
                <div class="text-xs mb-2">{{ resolveTraitDesc(trait) }}</div>
                <div class="text-[10px] opacity-80 border-t pt-1 border-gray-500">
                  {{ traitUnlockLabel(idx) }}{{ trait.active ? '' : ' · 尚未啟用' }}
                </div>
              </div>
            </template>
            <div 
              class="rounded px-0.5 md:px-2 py-0.5 md:py-1 text-[9px] md:text-xs text-center border cursor-pointer transition-all select-none truncate"
              :class="[
                getTraitColor(trait.rank),
                { 'opacity-50 saturate-50 scale-95': !trait.active, 'ring-1 ring-offset-1 ring-gray-200': !trait.active }
              ]"
            >
              {{ trait.name }}
            </div>
          </el-tooltip>
        </div>
      </div>
    </div>
    
    <!-- Equip Traits List (Add-on) -->
    <div v-if="hero" class="hidden md:grid mb-1 md:mb-2 px-1 md:px-2 md:order-4 md:grid-cols-2 md:gap-2 md:items-start">
       <span class="text-[10px] font-bold text-gray-500 ml-1 mb-1 md:col-span-2 md:mb-0.5">裝備特性:</span>
       <div class="grid grid-cols-4 md:grid-cols-4 gap-0.5 md:gap-1 md:col-span-2">
          <div
            v-for="(trait, idx) in equipTraits || [null, null, null, null]"
            :key="'eq'+idx"
            class="rounded px-0.5 md:px-1 py-0.5 md:py-0.5 text-[8px] md:text-[9px] text-center border border-dashed cursor-pointer transition-all select-none truncate hover:border-indigo-300 hover:bg-indigo-50 min-h-6 md:min-h-7 flex items-center justify-center"
            :class="trait ? getTraitColor(trait.rank) + ' border-solid' : 'border-gray-300 text-gray-400'"
            @click.stop="openEquipTraitSelect(idx)"
          >
            {{ trait ? trait.name : '+' }}
          </div>
       </div>
    </div>

    <!-- 兵學 Section -->
    <!-- md:order-2 puts this above radar/traits (order-3) and equip-traits (order-4).
         Shares order-2 with Skills Area below; DOM order keeps bingxue on top. -->
    <div v-if="hero" class="px-0 md:px-2 md:order-2">
      <BingxueSection
        :hero="hero"
        :model-value="bingxue || { direction: null, major: null, minors: [] }"
        @update:model-value="(v) => $emit('update:bingxue', v)"
      />
    </div>

    <!-- Skills Area -->
    <div class="flex flex-col gap-0.5 md:gap-2 md:order-2 md:flex-1 md:min-h-0">
      <!-- Unique Skill (Auto-filled) -->
      <el-popover
        placement="bottom"
        :offset="12"
        :title="hero?.unique_skill || '---'"
        :width="240"
        trigger="hover"
        :disabled="!hero?.unique_skill"
      >
        <template #reference>
          <div class="flex items-center gap-1 md:gap-2 p-0.5 md:p-2 bg-gray-50 rounded border border-gray-100 opacity-80">
            <div class="w-5 h-5 md:w-8 md:h-8 bg-yellow-100 rounded flex items-center justify-center text-[9px] md:text-xs font-bold text-yellow-700 flex-shrink-0">
              主
            </div>
            <div class="flex-1 min-w-0">
              <!-- Name + Tags on same line -->
              <div class="flex items-center gap-1 mb-0.5">
                <div class="text-[9px] md:text-sm text-gray-600 truncate">{{ hero?.unique_skill || '---' }}</div>
                <div v-if="uniqueSkillData?.tags?.length" class="hidden md:flex gap-0.5">
                  <span v-for="tag in uniqueSkillData.tags.slice(0, 2)" :key="tag" class="text-[7px] md:text-[8px] bg-blue-50 text-blue-600 px-0.5 rounded border border-blue-100 flex-shrink-0">{{ tag }}</span>
                </div>
              </div>
              <!-- Brief Description in larger font -->
              <BriefDescription v-if="uniqueSkillData?.brief_description" :text="uniqueSkillData.brief_description" class="text-[7px] md:text-sm italic" />
            </div>
          </div>
        </template>
        <div v-if="uniqueSkillData" class="text-xs space-y-2">
           <div class="flex justify-between items-start">
             <div class="font-bold text-indigo-600 flex flex-col">
                <span>{{ uniqueSkillData.type }}</span>
                <span v-if="uniqueSkillData.activation_rate" class="text-[10px] text-gray-500 mt-0.5">
                   發動機率 {{ formatRate(uniqueSkillData.activation_rate) }}
                </span>
             </div>
             <div class="flex items-center gap-1 scale-90 origin-top-right">
                <span class="text-[10px] text-gray-400">滿級</span>
                <el-switch v-model="isMaxLevel" size="small" />
             </div>
          </div>
          <SkillDescription
            :description="uniqueSkillData.description"
            :commander-description="uniqueSkillData.commander_description"
            :is-max-level="isMaxLevel"
            :vars="uniqueSkillData.vars"
          />
          <div v-if="uniqueSkillData.target" class="text-xs text-gray-400 italic mt-2">目標: {{ uniqueSkillData.target }}</div>
          <div v-if="uniqueSkillData.tags?.length" class="flex flex-wrap gap-1 mt-2">
            <span v-for="tag in uniqueSkillData.tags" :key="tag" class="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-100">{{ tag }}</span>
          </div>
        </div>
        <div v-else class="text-xs text-gray-500">
          <p>此武將的專屬固有戰法（資料庫中未找到詳細資訊）。</p>
        </div>
      </el-popover>

      <!-- Learnable Slot 1 -->
      <el-popover
        placement="bottom"
        :offset="12"
        :title="skill1?.name"
        :width="240"
        trigger="hover"
        :disabled="!skill1 || skillDragging"
      >
        <template #reference>
          <div
            class="flex items-center gap-1 md:gap-2 p-0.5 md:p-2 bg-white rounded border cursor-pointer transition-all"
            :class="[
              draggingSlot === 1 ? 'opacity-0' : '',
              isConflictSkill(skill1)
                ? 'ring-1 md:ring-2 ring-red-500 bg-red-50 border-red-500'
                : focusedSkillSlot === 1
                ? 'ring-1 md:ring-2 ring-indigo-500 bg-indigo-50 border-indigo-500'
                : dragOverSlot === 1
                  ? 'border-indigo-500 bg-indigo-100 ring-2 ring-indigo-400 scale-[1.02]'
                  : skillDragging
                    ? 'border-dashed border-indigo-300 bg-indigo-50'
                    : 'border-gray-200 hover:border-indigo-400'
            ]"
            :draggable="!!skill1"
            @click="$emit('open-skill-select', 1)"
            @dragstart="(e) => handleSkillDragStart(e, 1)"
            @dragend="draggingSlot = null; emit('skill-drag-end')"
            @dragover.prevent
            @dragenter="dragOverSlot = 1"
            @dragleave="(e) => { if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) dragOverSlot = null }"
            @drop="(e) => { dragOverSlot = null; handleDrop(e, 1) }"
          >
            <img v-if="skill1" :src="skill1.icon" class="w-5 h-5 md:w-8 md:h-8 rounded bg-gray-200 object-cover flex-shrink-0" />
            <div v-else class="w-5 h-5 md:w-8 md:h-8 bg-gray-100 rounded flex items-center justify-center text-gray-400 flex-shrink-0">
              <el-icon class="text-[10px] md:text-base"><Plus /></el-icon>
            </div>
            
            <div class="flex-1 min-w-0">
              <!-- Name + Tags on same line -->
              <div class="flex items-center gap-1 mb-0.5">
                <div v-if="skill1" class="text-[9px] md:text-sm font-bold text-gray-800 truncate">{{ skill1.name }}</div>
                <div v-else class="text-[9px] md:text-sm text-gray-400">習得</div>
                <div v-if="skill1?.tags?.length" class="hidden md:flex gap-0.5">
                  <span v-for="tag in skill1.tags.slice(0, 2)" :key="tag" class="text-[7px] md:text-[8px] bg-blue-50 text-blue-600 px-0.5 rounded border border-blue-100 flex-shrink-0">{{ tag }}</span>
                </div>
              </div>
              <!-- Brief Description in larger font -->
              <BriefDescription v-if="skill1?.brief_description" :text="skill1.brief_description" class="text-[7px] md:text-sm italic" />
            </div>
            <el-button v-if="skill1" link type="danger" size="small" class="!p-0 !h-auto" @click.stop="$emit('update:skill1', null)">
                <el-icon :size="10"><Close /></el-icon>
            </el-button>
          </div>
        </template>
        <div v-if="skill1" class="text-xs space-y-2">
          <div class="flex justify-between items-start">
             <div class="font-bold text-indigo-600 flex flex-col">
                <span>{{ skill1.type }}</span>
                <span v-if="skill1.activation_rate" class="text-[10px] text-gray-500 mt-0.5">
                  發動機率 {{ formatRate(skill1.activation_rate) }}
                </span>
             </div>
             <div class="flex items-center gap-1 scale-90 origin-top-right">
                <span class="text-[10px] text-gray-400">滿級</span>
                <el-switch v-model="isMaxLevel" size="small" />
             </div>
          </div>
          <SkillDescription
            :description="skill1.description"
            :commander-description="skill1.commander_description"
            :is-max-level="isMaxLevel"
            :vars="skill1.vars"
          />
          <div v-if="skill1.target" class="text-xs text-gray-400 italic mt-2">目標: {{ skill1.target }}</div>
          <div v-if="skill1.tags?.length" class="flex flex-wrap gap-1 mt-2">
            <span v-for="tag in skill1.tags" :key="tag" class="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-100">{{ tag }}</span>
          </div>
        </div>
      </el-popover>

      <!-- Learnable Slot 2 -->
      <el-popover
        placement="bottom"
        :offset="12"
        :title="skill2?.name"
        :width="240"
        trigger="hover"
        :disabled="!skill2 || skillDragging"
      >
        <template #reference>
          <div
            class="flex items-center gap-1 md:gap-2 p-0.5 md:p-2 bg-white rounded border cursor-pointer transition-all"
            :class="[
              draggingSlot === 2 ? 'opacity-0' : '',
              isConflictSkill(skill2)
                ? 'ring-1 md:ring-2 ring-red-500 bg-red-50 border-red-500'
                : focusedSkillSlot === 2
                ? 'ring-1 md:ring-2 ring-indigo-500 bg-indigo-50 border-indigo-500'
                : dragOverSlot === 2
                  ? 'border-indigo-500 bg-indigo-100 ring-2 ring-indigo-400 scale-[1.02]'
                  : skillDragging
                    ? 'border-dashed border-indigo-300 bg-indigo-50'
                    : 'border-gray-200 hover:border-indigo-400'
            ]"
            :draggable="!!skill2"
            @click="$emit('open-skill-select', 2)"
            @dragstart="(e) => handleSkillDragStart(e, 2)"
            @dragend="draggingSlot = null; emit('skill-drag-end')"
            @dragover.prevent
            @dragenter="dragOverSlot = 2"
            @dragleave="(e) => { if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) dragOverSlot = null }"
            @drop="(e) => { dragOverSlot = null; handleDrop(e, 2) }"
          >
            <img v-if="skill2" :src="skill2.icon" class="w-5 h-5 md:w-8 md:h-8 rounded bg-gray-200 object-cover flex-shrink-0" />
            <div v-else class="w-5 h-5 md:w-8 md:h-8 bg-gray-100 rounded flex items-center justify-center text-gray-400 flex-shrink-0">
              <el-icon class="text-[10px] md:text-base"><Plus /></el-icon>
            </div>
            
            <div class="flex-1 min-w-0">
              <!-- Name + Tags on same line -->
              <div class="flex items-center gap-1 mb-0.5">
                <div v-if="skill2" class="text-[9px] md:text-sm font-bold text-gray-800 truncate">{{ skill2.name }}</div>
                <div v-else class="text-[9px] md:text-sm text-gray-400">習得</div>
                <div v-if="skill2?.tags?.length" class="hidden md:flex gap-0.5">
                  <span v-for="tag in skill2.tags.slice(0, 2)" :key="tag" class="text-[7px] md:text-[8px] bg-blue-50 text-blue-600 px-0.5 rounded border border-blue-100 flex-shrink-0">{{ tag }}</span>
                </div>
              </div>
              <!-- Brief Description in larger font -->
              <BriefDescription v-if="skill2?.brief_description" :text="skill2.brief_description" class="text-[7px] md:text-sm italic" />
            </div>
             <el-button v-if="skill2" link type="danger" size="small" class="!p-0 !h-auto" @click.stop="$emit('update:skill2', null)">
                <el-icon :size="10"><Close /></el-icon>
            </el-button>
          </div>
        </template>
        <div v-if="skill2" class="text-xs space-y-2">
          <div class="flex justify-between items-start">
             <div class="font-bold text-indigo-600 flex flex-col">
                <span>{{ skill2.type }}</span>
                <span v-if="skill2.activation_rate" class="text-[10px] text-gray-500 mt-0.5">
                  發動機率 {{ formatRate(skill2.activation_rate) }}
                </span>
             </div>
             <div class="flex items-center gap-1 scale-90 origin-top-right">
                <span class="text-[10px] text-gray-400">滿級</span>
                <el-switch v-model="isMaxLevel" size="small" />
             </div>
          </div>
          <SkillDescription
            :description="skill2.description"
            :commander-description="skill2.commander_description"
            :is-max-level="isMaxLevel"
            :vars="skill2.vars"
          />
          <div v-if="skill2.target" class="text-xs text-gray-400 italic mt-2">目標: {{ skill2.target }}</div>
          <div v-if="skill2.tags?.length" class="flex flex-wrap gap-1 mt-2">
            <span v-for="tag in skill2.tags" :key="tag" class="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-100">{{ tag }}</span>
          </div>
        </div>
      </el-popover>
    </div>

    <!-- Stats Editor Dialog -->
    <el-dialog v-model="statsDialogVisible" title="自由屬性加點" width="360px" append-to-body align-center>
      <div class="flex flex-col gap-3">
        <div class="text-xs text-gray-500 flex justify-between">
          <span>剩餘可分配點數</span>
          <span class="font-bold" :class="localFreeRemaining < 0 ? 'text-red-500' : 'text-indigo-600'">{{ localFreeRemaining }} / 50</span>
        </div>
        <div class="space-y-2">
          <div v-for="(label, key) in statLabels" :key="key" class="flex items-center gap-1.5">
            <div class="w-8 text-xs font-bold text-gray-600">{{ label }}</div>
            <div class="text-xs text-gray-400 w-8 text-right">{{ heroBaseStats[key] }}</div>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localBonus[key] <= 0"
              @click="adjustBonus(key, -10)">-10</button>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localBonus[key] <= 0"
              @click="adjustBonus(key, -1)">-</button>
            <div class="w-10 text-center text-xs font-bold" :class="localBonus[key] > 0 ? 'text-green-600' : localBonus[key] < 0 ? 'text-red-500' : 'text-gray-400'">
              {{ localBonus[key] > 0 ? '+' : '' }}{{ localBonus[key] }}
            </div>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localFreeRemaining <= 0"
              @click="adjustBonus(key, 1)">+</button>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localFreeRemaining < 10"
              @click="adjustBonus(key, 10)">+10</button>
            <div class="w-8 text-xs font-bold text-right text-gray-800">{{ heroBaseStats[key] + localBonus[key] }}</div>
          </div>
        </div>
        <button class="text-xs text-gray-400 hover:text-red-500 self-end" @click="resetBonus">重置</button>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="statsDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveStats">確認修改</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Equip Trait Select Dialog -->
    <el-dialog v-model="equipTraitDialogVisible" title="選擇裝備特性" width="300px" append-to-body align-center>
      <div class="grid grid-cols-2 gap-2">
        <div 
           v-for="opt in MOCK_EQUIP_TRAITS" 
           :key="opt.name"
           class="p-2 border rounded cursor-pointer hover:bg-gray-50 text-center text-xs"
           @click="selectEquipTrait(opt)"
        >
          <div class="font-bold text-gray-700">{{ opt.name }}</div>
          <div class="text-[10px] text-gray-500">{{ opt.description }}</div>
        </div>
         <div 
           class="p-2 border rounded cursor-pointer hover:bg-red-50 text-center text-xs text-red-500 border-red-100"
           @click="selectEquipTrait(null as any)"
        >
          移除
        </div>
      </div>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { PropType, ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { Plus, Close, Edit, InfoFilled, Sort } from '@element-plus/icons-vue'
import HeroCard from './HeroCard.vue'
import RadarChart from './RadarChart.vue'
import SkillDescription from './SkillDescription.vue'
import BriefDescription from './BriefDescription.vue'
import BingxueSection from './BingxueSection.vue'
import type { BingxueActive } from '../composables/useLineups'
import { Hero, Skill, Trait, useData } from '../composables/useData'
import { useTemplateParser } from '../composables/useTemplateParser'

import { MOCK_EQUIP_TRAITS, TRANSPARENT_GIF, formatRate as _formatRate, getTraitColor } from '../constants/gameData'
import { TRAIT_UNLOCK } from '../constants/traits'

const props = defineProps({
  title: String,
  role: String,
  hero: Object as PropType<Hero | null>,
  skill1: Object as PropType<Skill | null>,
  skill2: Object as PropType<Skill | null>,
  stats: Object as PropType<any>,
  equipTraits: Array as PropType<Trait[]>,
  breakthrough: { type: Number, default: 0 },
  bingxue: { type: Object as PropType<BingxueActive>, default: () => ({ direction: null, major: null, minors: [] }) },
  focusedSkillSlot: Number as PropType<number | null>,
  isSwapSource: { type: Boolean, default: false },
  swapModeActive: { type: Boolean, default: false },
  isDragTarget: { type: Boolean, default: false },
  skillDragging: { type: Boolean, default: false },
  conflictingSkillNames: { type: Object as PropType<Set<string>>, default: () => new Set<string>() },
})

const isConflictSkill = (skill: Skill | null | undefined) =>
  !!skill && props.conflictingSkillNames.has(skill.name)

const { skills } = useData()
const { parseTextToPlain } = useTemplateParser()

const resolveTraitDesc = (trait: any) => {
  if (!trait?.description) return '說明: 尚未建立資料'
  return parseTextToPlain(trait.description, false, trait.vars)
}

const isMaxLevel = ref(true)
const dragOverSlot = ref<number | null>(null)
const draggingSlot = ref<number | null>(null)

const formatRate = (rateStr: string | undefined) => _formatRate(rateStr, isMaxLevel.value)

const uniqueSkillData = computed(() => {
  if (!props.hero?.unique_skill) return null
  const name = props.hero.unique_skill
  return skills.value.find(s => s.name === name || s.name_jp === name)
})

const emit = defineEmits([
  'update:hero', 
  'update:skill1', 
  'update:skill2',
  'update:stats',
  'update:equipTraits',
  'update:breakthrough',
  'update:bingxue',
  'open-hero-select',
  'open-skill-select',
  'skill-drop',
  'open-detail',
  'swap-click',
  'hero-drag-start',
  'hero-drag-end',
  'hero-drop',
  'skill-drag-start',
  'skill-drag-end',
  'skill-slot-drop'
])

const removeHero = () => {
  emit('update:hero', null)
  emit('update:skill1', null)
  emit('update:skill2', null)
  emit('update:equipTraits', [])
  emit('update:breakthrough', 0)
  emit('update:bingxue', { direction: null, major: null, minors: [] })
  // Reset stats to default not handled here explicitly but usually desired
}

const handleHeroDragStart = (event: DragEvent) => {
  if (!props.hero) return
  event.dataTransfer?.setData('application/hero-role', props.role as string)
  event.dataTransfer!.effectAllowed = 'move'
  emit('hero-drag-start')
}

const handleHeroDropEvent = (event: DragEvent) => {
  if (event.dataTransfer?.types.includes('application/hero-role')) {
    emit('hero-drop')
  }
}

// Stats Editing
// Base 50 free points, +10 per breakthrough star
const freePointsTotal = computed(() => 50 + (props.breakthrough ?? 0) * 10)
const statsDialogVisible = ref(false)
const STAT_KEYS = ['lea', 'val', 'int', 'pol', 'cha', 'spd'] as const

const heroBaseStats = computed(() => {
  const s = props.hero?.stats
  return {
    lea: s?.lea ?? 0, val: s?.val ?? 0, int: s?.int ?? 0,
    pol: s?.pol ?? 0, cha: s?.cha ?? 0, spd: s?.spd ?? 0,
  }
})

const statBonus = computed(() => {
  const base = heroBaseStats.value
  const result: Record<string, number> = {}
  for (const k of STAT_KEYS) result[k] = (props.stats[k] ?? 0) - base[k]
  return result
})

const freePointsRemaining = computed(() => {
  let used = 0
  for (const k of STAT_KEYS) used += Math.max(0, statBonus.value[k])
  return freePointsTotal.value - used
})

// Local editing state
const localBonus = ref<Record<string, number>>({})

const localFreeRemaining = computed(() => {
  let used = 0
  for (const k of STAT_KEYS) used += Math.max(0, localBonus.value[k] ?? 0)
  return freePointsTotal.value - used
})

const openStatsEditor = () => {
  if (!props.hero) return
  const b: Record<string, number> = {}
  for (const k of STAT_KEYS) b[k] = statBonus.value[k]
  localBonus.value = b
  statsDialogVisible.value = true
}

const adjustBonus = (key: string, delta: number) => {
  const current = localBonus.value[key] ?? 0
  const newVal = current + delta
  // Can't go below 0 (no negative bonus)
  if (newVal < 0) return
  // Can't exceed remaining free points (for positive delta)
  if (delta > 0 && delta > localFreeRemaining.value) return
  localBonus.value[key] = newVal
}

const resetBonus = () => {
  for (const k of STAT_KEYS) localBonus.value[k] = 0
}

const saveStats = () => {
  const base = heroBaseStats.value
  const result: Record<string, number> = {}
  for (const k of STAT_KEYS) result[k] = base[k] + (localBonus.value[k] ?? 0)
  emit('update:stats', result)
  statsDialogVisible.value = false
}

const statLabels: Record<string, string> = {
  lea: '統帥',
  val: '武勇',
  int: '智略',
  pol: '政務',
  cha: '魅力',
  spd: '速度'
}

const localTraits = computed<Trait[]>(() => {
  if (!props.hero) return []
  const existing = props.hero.traits || []
  const defaults: Trait[] = [
    { name: '固有', rank: 'S', active: true },
    { name: '特性 2', rank: 'A', active: false },
    { name: '特性 3', rank: 'B', active: false },
    { name: '特性 4', rank: 'C', active: false },
  ]
  return defaults.map((def, i) => {
    const base = existing[i] ? { ...existing[i] } : def
    return { ...base, active: props.breakthrough >= TRAIT_UNLOCK[i] }
  })
})

const traitUnlockLabel = (idx: number) => {
  const req = TRAIT_UNLOCK[idx]
  if (req === 0) return '固有特性 (永久生效)'
  return `需要 ${req} 星突破解鎖`
}

// Max breakthrough is capped by rarity: S(5★)→5, A(4★)→4, B(3★)→3.
const maxBreakthrough = computed(() => {
  const r = Number(props.hero?.rarity ?? 0)
  if (r >= 5) return 5
  if (r === 4) return 4
  return 3
})

watch(() => props.hero, (newHero, oldHero) => {
  if (newHero?.stats) {
    emit('update:stats', { ...newHero.stats })
  }
  // Reset breakthrough when swapping to a different hero (not on initial mount)
  if (oldHero && newHero?.name !== oldHero?.name) {
    emit('update:breakthrough', 0)
  } else if (newHero && props.breakthrough > maxBreakthrough.value) {
    // Clamp on initial load if persisted value exceeds the new cap
    emit('update:breakthrough', maxBreakthrough.value)
  }
}, { immediate: true })

// Breakthrough stars: click star N → set to N; click the current value → reset to 0.
const setBreakthrough = (n: number) => {
  if (n > maxBreakthrough.value) return
  const next = props.breakthrough === n ? 0 : n
  emit('update:breakthrough', next)
}

// Track viewport so the mobile-only popover is fully removed from DOM on desktop
// (el-popover's reference wrapper ignores md:hidden, leaving a ghost star visible).
const isDesktop = ref(false)
let mq: MediaQueryList | null = null
const updateIsDesktop = (e: MediaQueryListEvent | MediaQueryList) => {
  isDesktop.value = e.matches
}
onMounted(() => {
  mq = window.matchMedia('(min-width: 768px)')
  isDesktop.value = mq.matches
  mq.addEventListener('change', updateIsDesktop)
})
onBeforeUnmount(() => {
  mq?.removeEventListener('change', updateIsDesktop)
})

// Hover-fill preview: when hovering star n, show n stars lit regardless of breakthrough.
const hoverStar = ref(0)

// Mobile popover ref so we can dismiss after a pick.
const popoverRef = ref<any>(null)
const onMobilePickStar = (n: number) => {
  const wasReset = props.breakthrough === n
  setBreakthrough(n)
  // Keep popover open if user clicked the current value (reset gesture); else close.
  if (!wasReset) popoverRef.value?.hide?.()
}
const displayStarCount = computed(() =>
  hoverStar.value > 0 ? hoverStar.value : props.breakthrough
)

// Equip Traits Logic
const equipTraitDialogVisible = ref(false)
const currentEquipSlotIdx = ref<number | null>(null)

const openEquipTraitSelect = (idx: number) => {
  currentEquipSlotIdx.value = idx
  equipTraitDialogVisible.value = true
}

const selectEquipTrait = (trait: Trait | null) => {
  if (currentEquipSlotIdx.value === null) return
  
  // Clone current traits or create new array if empty
  const currentTraits = props.equipTraits ? [...props.equipTraits] : [null, null, null, null]
  currentTraits[currentEquipSlotIdx.value] = trait as any
  
  emit('update:equipTraits', currentTraits)
  equipTraitDialogVisible.value = false
}

const handleSkillDragStart = (event: DragEvent, slotIdx: number) => {
  const skill = slotIdx === 1 ? props.skill1 : props.skill2
  event.dataTransfer?.setData('application/skill-slot', JSON.stringify({ role: props.role, slotIdx }))
  event.dataTransfer!.effectAllowed = 'move'
  const ghost = new Image()
  ghost.src = TRANSPARENT_GIF
  event.dataTransfer?.setDragImage(ghost, 0, 0)
  draggingSlot.value = slotIdx
  emit('skill-drag-start', skill)
}

const handleDrop = (event: DragEvent, targetSlotIdx: number) => {
  event.preventDefault()
  if (event.dataTransfer?.types.includes('application/skill-slot')) {
    const src = JSON.parse(event.dataTransfer.getData('application/skill-slot'))
    emit('skill-slot-drop', src.role, src.slotIdx, targetSlotIdx)
    return
  }
  const skillData = event.dataTransfer?.getData('application/json')
  if (skillData) {
    try {
      const skill = JSON.parse(skillData)
      emit('skill-drop', targetSlotIdx, skill)
    } catch (e) {
      console.error('Invalid skill drop data')
    }
  }
}
</script>

<style scoped>
.breakthrough-star {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 1px;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.2s ease;
}
.breakthrough-star .break-star-svg {
  fill: #e5e7eb; /* gray-200 */
  stroke: #9ca3af; /* gray-400 */
  stroke-width: 1.2;
  stroke-linejoin: round;
  transition: fill 0.25s ease, stroke 0.2s ease, transform 0.2s ease;
}
.breakthrough-star:hover {
  transform: scale(1.18) rotate(-4deg);
}
.breakthrough-star:hover .break-star-svg {
  fill: #fde68a; /* preview amber-200 */
  stroke: #f59e0b;
}
.breakthrough-star.is-filled .break-star-svg {
  fill: url(#breakStarGrad);
  stroke: #7f1d1d; /* red-900 outline for definition */
  stroke-width: 1;
}
.breakthrough-star.is-filled {
  animation: break-star-pop 0.35s ease;
}
.breakthrough-star.is-filled:hover {
  transform: scale(1.22) rotate(-6deg);
}
@keyframes break-star-pop {
  0%   { transform: scale(0.6) rotate(-20deg); }
  60%  { transform: scale(1.25) rotate(6deg); }
  100% { transform: scale(1) rotate(0); }
}
</style>