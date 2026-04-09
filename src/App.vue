<template>
  <el-container class="w-full bg-slate-50" style="height: 100dvh">
    <el-header class="bg-white border-b border-gray-200 flex items-center justify-between px-4 sticky top-0 z-50">
      <div class="flex items-center gap-4">
        <!-- Mobile Menu Button -->
        <el-button class="md:hidden" text @click="mobileSidebarVisible = true">
          <el-icon :size="24"><Menu /></el-icon>
        </el-button>

        <div class="flex items-center gap-2">
          <el-icon :size="24" class="text-indigo-600 hidden md:block"><Flag /></el-icon>
          <!-- Editable Team Name / Inventory Title -->
          <div v-if="!isEditingInventory" class="flex items-center gap-2">
             <el-input 
               v-model="currentTeamName" 
               placeholder="輸入隊伍名稱" 
               class="w-32 sm:w-48 font-bold"
               size="default"
             >
               <template #suffix>
                 <el-icon class="el-input__icon"><Edit /></el-icon>
               </template>
             </el-input>
          </div>
          <div v-else class="font-bold text-gray-800 text-lg">
            庫存編輯模式
          </div>
        </div>
        
        <!-- Cost Display -->
        <div v-if="!isEditingInventory" class="text-xs font-bold bg-gray-100 px-3 py-1.5 rounded-full border border-gray-200 flex items-center hidden sm:flex">
           <span class="text-gray-500 mr-1">Cost:</span>
           <span :class="{'text-red-500': totalCost > 20, 'text-gray-800': totalCost <= 20}" class="text-sm">{{ totalCost }}/20</span>
        </div>
        <!-- Troop Level Chips -->
        <div v-if="!isEditingInventory" class="text-xs font-bold bg-gray-100 px-2 py-1 rounded-full border border-gray-200 items-center gap-1 hidden sm:flex">
           <span class="text-gray-500 mr-0.5">兵:</span>
           <span
             v-for="tt in TROOP_TYPES"
             :key="tt"
             class="px-1 rounded text-[10px]"
             :class="troopLevels[tt] > 0 ? 'text-amber-700 bg-amber-50' : 'text-gray-400'"
           >{{ TROOP_LABELS[tt] }}{{ troopLevels[tt] }}</span>
        </div>
      </div>

      <div>
        <template v-if="!isEditingInventory">
          <el-button type="info" round plain @click="startEditingInventory" class="hidden sm:inline-flex">
            <el-icon class="mr-1"><Edit /></el-icon> 編輯庫存
          </el-button>
          <el-button type="info" circle plain @click="startEditingInventory" class="sm:hidden">
            <el-icon><Edit /></el-icon>
          </el-button>

          <el-button type="primary" round plain @click="openShareDialog" class="hidden sm:inline-flex">
            <el-icon class="mr-1"><Share /></el-icon> 分享
          </el-button>
          <el-button type="primary" circle plain @click="openShareDialog" class="sm:hidden">
            <el-icon><Share /></el-icon>
          </el-button>

          <el-button type="danger" round plain @click="openResetDialog" class="hidden sm:inline-flex">
            <el-icon class="mr-1"><Delete /></el-icon> 重置
          </el-button>
           <el-button type="danger" circle plain @click="openResetDialog" class="sm:hidden">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
        <template v-else>
          <el-button round @click="cancelEditingInventory">
            <el-icon class="mr-1"><Close /></el-icon> <span class="hidden sm:inline">不儲存離開</span>
          </el-button>
          <el-button type="success" round @click="saveInventory">
            <el-icon class="mr-1"><Check /></el-icon> <span class="hidden sm:inline">儲存庫存</span>
          </el-button>
        </template>
      </div>
    </el-header>

    <el-main class="p-0 overflow-hidden" style="height: calc(100dvh - 60px - 32px)">
      
      <!-- View 1: Lineup Builder (Default) -->
      <div v-if="!isEditingInventory" class="flex flex-col md:flex-row h-full">
        <!-- Left Sidebar: Team List (Desktop) -->
        <div class="hidden md:flex w-20 bg-gray-900 flex-col items-center py-4 gap-4 flex-shrink-0 z-50">
          <div 
            v-for="(team, idx) in lineups" 
            :key="idx"
            class="w-12 h-12 rounded-full border-2 cursor-pointer flex items-center justify-center text-white font-bold transition-all relative group"
            :class="currentTeamIndex === idx ? 'border-indigo-500 bg-gray-800' : 'border-gray-600 hover:border-gray-400 bg-gray-800'"
            @click="currentTeamIndex = idx"
          >
            <img 
              v-if="team.main.hero" 
              :src="team.main.hero.portrait" 
              class="w-full h-full rounded-full object-cover opacity-80"
            />
            <span v-else>{{ idx + 1 }}</span>
            
            <div class="absolute left-full ml-2 bg-gray-900 text-white text-xs px-3 py-2 rounded w-max opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-xl border border-gray-700">
              <div class="font-bold border-b border-gray-700 pb-1 mb-1 text-indigo-300">{{ team.name }}</div>
              <div class="space-y-0.5 text-gray-300">
                <div>大將: {{ team.main.hero?.name || '-' }}</div>
                <div>副將: {{ team.vice1.hero?.name || '-' }}</div>
                <div>副將: {{ team.vice2.hero?.name || '-' }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Mobile Sidebar Drawer -->
        <el-drawer
          v-model="mobileSidebarVisible"
          direction="ltr"
          size="280px"
          :with-header="false"
          class="bg-gray-900"
        >
          <div class="h-full bg-gray-900 p-4 flex flex-col gap-4">
             <div class="text-white font-bold text-lg border-b border-gray-700 pb-2 mb-2">隊伍列表</div>
             <div 
                v-for="(team, idx) in lineups" 
                :key="idx"
                class="flex items-center gap-3 p-2 rounded cursor-pointer transition-colors"
                :class="currentTeamIndex === idx ? 'bg-gray-800 border border-indigo-500' : 'hover:bg-gray-800 border border-transparent'"
                @click="{ currentTeamIndex = idx; mobileSidebarVisible = false; }"
              >
                <div class="w-10 h-10 rounded-full border-2 border-gray-600 flex items-center justify-center text-white font-bold bg-gray-700 overflow-hidden">
                   <img 
                    v-if="team.main.hero" 
                    :src="team.main.hero.portrait" 
                    class="w-full h-full object-cover"
                  />
                  <span v-else>{{ idx + 1 }}</span>
                </div>
                <div class="flex-1">
                   <div class="text-indigo-300 font-bold text-sm">{{ team.name }}</div>
                   <div class="text-gray-400 text-xs truncate">
                     {{ team.main.hero?.name || '無大將' }} / {{ team.vice1.hero?.name || '-' }} / {{ team.vice2.hero?.name || '-' }}
                   </div>
                </div>
                <el-icon v-if="currentTeamIndex === idx" class="text-indigo-500"><Check /></el-icon>
             </div>
          </div>
        </el-drawer>

                <!-- Center: Lineup Builder Area -->
                <div class="flex-1 flex flex-col md:flex-row h-full overflow-hidden">
                  <div
                    class="flex-none md:flex-1 overflow-y-auto p-0.5 md:p-6 bg-slate-50"
                    @click.self="clearSkillFocus"
                  >
                     <!-- Mobile: Compact Grid | Desktop: Grid -->
                     <div
                       class="grid grid-cols-3 md:grid-cols-3 lg:grid-cols-3 gap-0.5 md:gap-4 pb-0 md:pb-0 h-auto"
                       :class="{ 'lineup-shake': lineupShakeActive }"
                       @click.self="clearSkillFocus"
                       @animationend="lineupShakeActive = false"
                     >
                        <div class="w-full md:min-w-0 md:h-full">
                          <LineupSlot
                            title="大將"
                            role="main"
                            v-model:hero="currentLineup.main.hero"
                            v-model:skill1="currentLineup.main.skill1"
                            v-model:skill2="currentLineup.main.skill2"
                            v-model:stats="currentLineup.main.stats"
                            v-model:equipTraits="currentLineup.main.equipTraits"
                            v-model:breakthrough="currentLineup.main.breakthrough"
                            :focused-skill-slot="currentSelectingSkillRole === 'main' ? currentSelectingSkillSlot : null"
                            :is-swap-source="swapModeRole === 'main'"
                            :swap-mode-active="swapModeRole !== null"
                            :is-drag-target="dragSourceRole !== null && dragSourceRole !== 'main'"
                            :skill-dragging="isSkillDragging"
                            :conflicting-skill-names="conflictingSkillNames"
                            @open-hero-select="openHeroSelect('main')"
                            @open-skill-select="(slotIdx) => handleSkillSlotClick('main', slotIdx)"
                            @skill-drop="(slotIdx, skill) => handleSkillDrop('main', slotIdx, skill)"
                            @skill-drag-start="handleSkillDragStarted"
                            @skill-drag-end="handleSkillDragEnded"
                            @skill-slot-drop="(srcRole, srcSlot, tgtSlot) => handleSkillSlotDrop('main', srcRole, srcSlot, tgtSlot)"
                            @open-detail="openMobileDetail('main')"
                            @swap-click="handleSwapAction('main')"
                            @hero-drag-start="() => dragSourceRole = 'main'"
                            @hero-drag-end="() => dragSourceRole = null"
                            @hero-drop="() => handleHeroDrop('main')"
                          />
                        </div>
                        <div class="w-full md:min-w-0 md:h-full">
                          <LineupSlot
                            title="副將"
                            role="vice1"
                            v-model:hero="currentLineup.vice1.hero"
                            v-model:skill1="currentLineup.vice1.skill1"
                            v-model:skill2="currentLineup.vice1.skill2"
                            v-model:stats="currentLineup.vice1.stats"
                            v-model:equipTraits="currentLineup.vice1.equipTraits"
                            v-model:breakthrough="currentLineup.vice1.breakthrough"
                            :focused-skill-slot="currentSelectingSkillRole === 'vice1' ? currentSelectingSkillSlot : null"
                            :is-swap-source="swapModeRole === 'vice1'"
                            :swap-mode-active="swapModeRole !== null"
                            :is-drag-target="dragSourceRole !== null && dragSourceRole !== 'vice1'"
                            :skill-dragging="isSkillDragging"
                            :conflicting-skill-names="conflictingSkillNames"
                            @open-hero-select="openHeroSelect('vice1')"
                            @open-skill-select="(slotIdx) => handleSkillSlotClick('vice1', slotIdx)"
                            @skill-drop="(slotIdx, skill) => handleSkillDrop('vice1', slotIdx, skill)"
                            @skill-drag-start="handleSkillDragStarted"
                            @skill-drag-end="handleSkillDragEnded"
                            @skill-slot-drop="(srcRole, srcSlot, tgtSlot) => handleSkillSlotDrop('vice1', srcRole, srcSlot, tgtSlot)"
                            @open-detail="openMobileDetail('vice1')"
                            @swap-click="handleSwapAction('vice1')"
                            @hero-drag-start="() => dragSourceRole = 'vice1'"
                            @hero-drag-end="() => dragSourceRole = null"
                            @hero-drop="() => handleHeroDrop('vice1')"
                          />
                        </div>
                        <div class="w-full md:min-w-0 md:h-full">
                          <LineupSlot
                            title="副將"
                            role="vice2"
                            v-model:hero="currentLineup.vice2.hero"
                            v-model:skill1="currentLineup.vice2.skill1"
                            v-model:skill2="currentLineup.vice2.skill2"
                            v-model:stats="currentLineup.vice2.stats"
                            v-model:equipTraits="currentLineup.vice2.equipTraits"
                            v-model:breakthrough="currentLineup.vice2.breakthrough"
                            :focused-skill-slot="currentSelectingSkillRole === 'vice2' ? currentSelectingSkillSlot : null"
                            :is-swap-source="swapModeRole === 'vice2'"
                            :swap-mode-active="swapModeRole !== null"
                            :is-drag-target="dragSourceRole !== null && dragSourceRole !== 'vice2'"
                            :skill-dragging="isSkillDragging"
                            :conflicting-skill-names="conflictingSkillNames"
                            @open-hero-select="openHeroSelect('vice2')"
                            @open-skill-select="(slotIdx) => handleSkillSlotClick('vice2', slotIdx)"
                            @skill-drop="(slotIdx, skill) => handleSkillDrop('vice2', slotIdx, skill)"
                            @skill-drag-start="handleSkillDragStarted"
                            @skill-drag-end="handleSkillDragEnded"
                            @skill-slot-drop="(srcRole, srcSlot, tgtSlot) => handleSkillSlotDrop('vice2', srcRole, srcSlot, tgtSlot)"
                            @open-detail="openMobileDetail('vice2')"
                            @swap-click="handleSwapAction('vice2')"
                            @hero-drag-start="() => dragSourceRole = 'vice2'"
                            @hero-drag-end="() => dragSourceRole = null"
                            @hero-drop="() => handleHeroDrop('vice2')"
                          />
                        </div>
                     </div>
                  </div>
        
                                      <!-- Right: Library (Select Mode) - On mobile this is below the lineups -->
        
                                      <div class="flex-1 md:flex-none md:h-full w-full md:w-[35%] bg-white border-t md:border-t-0 md:border-l border-gray-200 flex flex-col shadow-xl z-40 min-h-0">
        
                                        <el-tabs v-model="activeTab" class="flex-1 flex flex-col px-4 pt-2" stretch>                                <el-tab-pane label="武將庫" name="heroes" class="h-full flex flex-col overflow-hidden">
                                   <HeroLibrary 
                                     mode="select" 
                                     :used-heroes="allUsedHeroNames" 
                                     :owned-heroes="ownedHeroes"
                                     :filter-owned="showOwnedOnly"
                                     @update:filterOwned="val => showOwnedOnly = val"
                                     @select="selectHeroFromLibrary" 
                                   />
                                </el-tab-pane>
                                <el-tab-pane label="戰法庫" name="skills" class="h-full flex flex-col overflow-hidden">
                                   <SkillLibrary
                                     mode="select"
                                     :used-skills="allUsedSkillNames"
                                     :owned-skills="ownedSkills"
                                     :filter-owned="showOwnedOnly"
                                     @update:filterOwned="val => showOwnedOnly = val"
                                     @select="selectSkillFromDialog"
                                     @skill-drag-start="handleSkillDragStarted"
                                     @skill-drag-end="handleSkillDragEnded"
                                   /> 
                                </el-tab-pane>          
                     </el-tabs>
                  </div>
                </div>
              </div>
        
              <!-- View 2: Inventory Editor (Full Screen Mode) -->
              <div v-else class="h-full bg-white flex flex-col">
                <div class="container mx-auto h-full flex flex-col p-4">
                  <el-tabs v-model="inventoryActiveTab" class="flex-1 flex flex-col" type="border-card">
                    <el-tab-pane label="武將庫存" name="heroes" class="h-full flex flex-col overflow-hidden">
                       <HeroLibrary 
                         mode="manage" 
                         :used-heroes="[]" 
                         :owned-heroes="tempOwnedHeroes"
                         @update:ownedHeroes="val => tempOwnedHeroes = val"
                       />
                    </el-tab-pane>
                    <el-tab-pane label="戰法庫存" name="skills" class="h-full flex flex-col overflow-hidden">
                       <SkillLibrary 
                         mode="manage" 
                         :used-skills="[]" 
                         :owned-skills="tempOwnedSkills"
                         @update:ownedSkills="val => tempOwnedSkills = val"
                       />
                    </el-tab-pane>
                  </el-tabs>
                </div>
              </div>
        
            </el-main>
        
                <!-- Mobile Detail Drawer -->
        
                <el-drawer
        
                  v-model="mobileDetailVisible"
        
                  direction="btt"
        
                  size="60%"
        
                  :with-header="false"
        
                  class="rounded-t-xl overflow-hidden"
        
                >
        
                  <MobileSlotDetail 
        
                    v-if="currentDetailRole"
        
                    :role-name="currentDetailRole === 'main' ? '大將' : '副將'"
        
                    :hero="currentLineup[currentDetailRole].hero"
        
                    :stats="currentLineup[currentDetailRole].stats"
        
                    :equip-traits="currentLineup[currentDetailRole].equipTraits"
        
                    @update:hero="(h) => currentLineup[currentDetailRole!].hero = h"
        
                    @open-equip="(idx) => openEquipDialog(currentDetailRole!, idx)"
        
                  />
        
                </el-drawer>
        
            
        
                <!-- Equip Trait Dialog (Mobile) -->
        
                <el-dialog v-model="equipDialogVisible" title="選擇裝備特性" width="300px" align-center append-to-body>
        
                  <div class="grid grid-cols-2 gap-2">
        
                    <div 
        
                       v-for="opt in MOCK_EQUIP_TRAITS" 
        
                       :key="opt.name"
        
                       class="p-2 border rounded cursor-pointer hover:bg-gray-50 text-center text-xs"
        
                       @click="handleEquipSelect(opt)"
        
                    >
        
                      <div class="font-bold text-gray-700">{{ opt.name }}</div>
        
                      <div class="text-[10px] text-gray-500">{{ opt.description }}</div>
        
                    </div>
        
                     <div 
        
                       class="p-2 border rounded cursor-pointer hover:bg-red-50 text-center text-xs text-red-500 border-red-100"
        
                       @click="handleEquipSelect(null)"
        
                    >
        
                      移除
        
                    </div>
        
                  </div>
        
                </el-dialog>
        
            
        
                <!-- Dialogs -->    <el-dialog 
      v-model="skillSelectDialogVisible" 
      title="選擇戰法" 
      width="90%" 
      class="max-w-md skill-select-dialog"
      align-center
    >
      <div class="h-[60vh]">
        <SkillLibrary :mode="'select'" :used-skills="allUsedSkillNames" :owned-skills="ownedSkills" @select="selectSkillFromDialog" />
      </div>
    </el-dialog>

    <!-- Share Dialog -->
    <el-dialog v-model="shareDialogVisible" title="分享配置" width="320px" align-center>
      <div class="flex flex-col gap-3">
        <el-button type="primary" plain size="large" @click="shareLineup('all')" class="w-full !m-0">
          <div class="flex flex-col items-center">
            <span class="font-bold">分享全部</span>
            <span class="text-xs opacity-80">所有隊伍 + 庫存 (備份用)</span>
          </div>
        </el-button>
        <el-button type="success" plain size="large" @click="shareLineup('current')" class="w-full !m-0">
           <div class="flex flex-col items-center">
            <span class="font-bold">分享當前隊伍</span>
            <span class="text-xs opacity-80">僅分享目前編輯的隊伍 1 隊</span>
          </div>
        </el-button>
         <el-button type="warning" plain size="large" @click="shareLineup('inventory')" class="w-full !m-0">
           <div class="flex flex-col items-center">
            <span class="font-bold">僅分享庫存</span>
            <span class="text-xs opacity-80">請教他人配將用</span>
          </div>
        </el-button>
      </div>
    </el-dialog>

    <!-- Reset Dialog -->
    <el-dialog v-model="resetDialogVisible" title="重置選項" width="320px" align-center>
      <div class="flex flex-col gap-3">
        <el-button type="danger" plain size="large" @click="clearLineup('current')" class="w-full !m-0">
          <div class="flex flex-col items-center">
            <span class="font-bold">重置當前隊伍</span>
            <span class="text-xs opacity-80">僅清空目前顯示的隊伍</span>
          </div>
        </el-button>
        <el-button type="warning" plain size="large" @click="clearLineup('inventory')" class="w-full !m-0">
           <div class="flex flex-col items-center">
            <span class="font-bold">清空庫存</span>
            <span class="text-xs opacity-80">移除所有已標記的擁有武將</span>
          </div>
        </el-button>
         <el-button type="danger" size="large" @click="clearLineup('all')" class="w-full !m-0">
           <div class="flex flex-col items-center">
            <span class="font-bold">全部重置</span>
            <span class="text-xs opacity-80">清空所有隊伍與庫存 (慎用)</span>
          </div>
        </el-button>
      </div>
    </el-dialog>

    <el-footer class="bg-white border-t border-gray-200 flex items-center justify-center text-xs text-gray-400 h-8 gap-2">
      <span>聯絡作者: yt.neko.vision@gmail.com</span>
      <span class="opacity-50">|</span>
      <span>Discord: neko.vision</span>
    </el-footer>

  </el-container>

  <!-- Skill drag preview -->
  <Teleport to="body">
    <div v-if="draggingSkill"
      class="fixed z-[9999] pointer-events-none select-none"
      :style="{ left: dragPos.x + 16 + 'px', top: dragPos.y - 8 + 'px' }"
    >
      <div class="bg-white rounded-xl shadow-2xl border-2 border-indigo-400 p-3 w-64 max-h-72 overflow-hidden">
        <div class="flex items-center gap-2 mb-2">
          <img :src="draggingSkill.icon" class="w-10 h-10 rounded-lg bg-gray-100 object-cover flex-shrink-0" />
          <div class="min-w-0">
            <div class="font-bold text-sm text-gray-800 truncate">{{ draggingSkill.name }}</div>
            <div class="flex items-center gap-1 mt-0.5">
              <span class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{{ draggingSkill.type }}</span>
              <span v-if="draggingSkill.rarity === 'S'" class="text-xs font-bold text-yellow-600">S</span>
              <span v-if="draggingSkill.activation_rate" class="text-[10px] text-gray-400">{{ draggingSkill.activation_rate }}</span>
            </div>
          </div>
        </div>
        <SkillDescription
          :description="draggingSkill.description"
          :commander-description="draggingSkill.commander_description"
          :is-max-level="true"
          :vars="draggingSkill.vars"
        />
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Flag, Share, Delete, Edit, Close, Check, Menu } from '@element-plus/icons-vue'
import LineupSlot from './components/LineupSlot.vue'
import SkillDescription from './components/SkillDescription.vue'
import HeroLibrary from './components/HeroLibrary.vue'
import SkillLibrary from './components/SkillLibrary.vue'
import MobileSlotDetail from './components/MobileSlotDetail.vue'

import { useData, Hero, Skill, Trait } from './composables/useData'
import { MOCK_EQUIP_TRAITS, ShareableData, ShareableLineup } from './constants/gameData'
import { useLineups, type RoleData } from './composables/useLineups'
import { useTroopLevels } from './composables/useTroopLevels'
import { TROOP_TYPES, TROOP_LABELS } from './constants/traits'
import { useInventory } from './composables/useInventory'

const { 
  lineups, 
  currentTeamIndex, 
  currentLineup, 
  currentTeamName, 
  allUsedHeroNames, 
  allUsedSkillNames, 
  totalCost,
  clearLineup: clearLineupData,
  swapRoles
} = useLineups()

const troopLevels = useTroopLevels(currentLineup)

const {
  ownedHeroes,
  ownedSkills,
  showOwnedOnly,
  isEditingInventory,
  tempOwnedHeroes,
  tempOwnedSkills,
  startEditingInventory,
  saveInventory,
  cancelEditingInventory,
  clearInventory
} = useInventory()

// Equip Traits Logic (Shared / Mobile)
const equipDialogVisible = ref(false)
const currentEquipRole = ref<Role | null>(null)
const currentEquipSlotIdx = ref<number | null>(null)

const openEquipDialog = (role: Role, idx: number) => {
  currentEquipRole.value = role
  currentEquipSlotIdx.value = idx
  equipDialogVisible.value = true
}

const handleEquipSelect = (trait: Trait | null) => {
  if (currentEquipRole.value && currentEquipSlotIdx.value !== null) {
    const role = currentLineup.value[currentEquipRole.value]
    // Ensure array exists
    if (!role.equipTraits) role.equipTraits = [null, null, null, null]
    
    // Create new array to trigger reactivity
    const newTraits = [...role.equipTraits]
    newTraits[currentEquipSlotIdx.value] = trait ? { ...trait } : null // clone to avoid reference issues
    role.equipTraits = newTraits
    
    equipDialogVisible.value = false
  }
}

const activeTab = ref('heroes')
const skillSelectDialogVisible = ref(false)

const inventoryActiveTab = ref('heroes')

// Interaction State
type Role = 'main' | 'vice1' | 'vice2'
const currentSelectingHeroRole = ref<Role | null>(null)
const currentSelectingSkillRole = ref<Role | null>(null)
const currentSelectingSkillSlot = ref<number | null>(null)

// Swap State
const swapModeRole = ref<Role | null>(null)
const dragSourceRole = ref<Role | null>(null)

// Skill drag preview
const draggingSkill = ref<Skill | null>(null)
const dragPos = ref({ x: 0, y: 0 })
const isSkillDragging = computed(() => draggingSkill.value !== null)

const onDragOverDoc = (e: DragEvent) => {
  dragPos.value = { x: e.clientX, y: e.clientY }
}

const handleSkillDragStarted = (skill: Skill) => {
  draggingSkill.value = skill
  document.addEventListener('dragover', onDragOverDoc)
}

const handleSkillDragEnded = () => {
  draggingSkill.value = null
  document.removeEventListener('dragover', onDragOverDoc)
}

// Mobile Detail State
const mobileDetailVisible = ref(false)
const currentDetailRole = ref<Role | null>(null)

// UI State
const mobileSidebarVisible = ref(false)

// Actions
const handleSwapAction = (role: Role) => {
  if (swapModeRole.value === null) {
    swapModeRole.value = role
  } else if (swapModeRole.value === role) {
    swapModeRole.value = null
  } else {
    swapRoles(swapModeRole.value, role)
    swapModeRole.value = null
    ElMessage.success('已交換槽位')
  }
}

const handleHeroDrop = (targetRole: Role) => {
  if (dragSourceRole.value && dragSourceRole.value !== targetRole) {
    swapRoles(dragSourceRole.value, targetRole)
    ElMessage.success('已交換槽位')
  }
  dragSourceRole.value = null
}

const openHeroSelect = (role: Role) => {
  if (swapModeRole.value !== null) {
    handleSwapAction(role)
    return
  }
  currentSelectingHeroRole.value = role
  activeTab.value = 'heroes'
}

const openMobileDetail = (role: Role) => {
  currentDetailRole.value = role
  mobileDetailVisible.value = true
}

const handleSkillSlotClick = (role: Role, slotIdx: number) => {
  currentSelectingSkillRole.value = role
  currentSelectingSkillSlot.value = slotIdx
  activeTab.value = 'skills'
}

const handleSkillDrop = (role: Role, slotIdx: number, skill: Skill) => {
  const targetRole = currentLineup.value[role]
  if (slotIdx === 1) targetRole.skill1 = skill
  if (slotIdx === 2) targetRole.skill2 = skill
  ElMessage.success(`已習得 ${skill.name}`)
}

const handleSkillSlotDrop = (targetRole: Role, sourceRole: Role, sourceSlotIdx: number, targetSlotIdx: number) => {
  const src = currentLineup.value[sourceRole]
  const tgt = currentLineup.value[targetRole]
  const srcSkill = sourceSlotIdx === 1 ? src.skill1 : src.skill2
  const tgtSkill = targetSlotIdx === 1 ? tgt.skill1 : tgt.skill2
  if (targetSlotIdx === 1) tgt.skill1 = srcSkill
  else tgt.skill2 = srcSkill
  if (sourceSlotIdx === 1) src.skill1 = tgtSkill
  else src.skill2 = tgtSkill
}

const selectHeroFromLibrary = (hero: Hero) => {
  if (currentSelectingHeroRole.value) {
    currentLineup.value[currentSelectingHeroRole.value].hero = hero
    ElMessage.success(`已選擇 ${hero.name}`)
  } else {
    if (!currentLineup.value.main.hero) currentLineup.value.main.hero = hero
    else if (!currentLineup.value.vice1.hero) currentLineup.value.vice1.hero = hero
    else if (!currentLineup.value.vice2.hero) currentLineup.value.vice2.hero = hero
    else currentLineup.value.main.hero = hero 
  }
}

const SKILL_SLOT_SEQUENCE: {r: Role, s: 1 | 2}[] = [
  {r: 'main', s: 1}, {r: 'main', s: 2},
  {r: 'vice1', s: 1}, {r: 'vice1', s: 2},
  {r: 'vice2', s: 1}, {r: 'vice2', s: 2},
]

const advanceFocus = () => {
  const currentIdx = SKILL_SLOT_SEQUENCE.findIndex(
    item => item.r === currentSelectingSkillRole.value && item.s === currentSelectingSkillSlot.value
  )
  if (currentIdx !== -1 && currentIdx < SKILL_SLOT_SEQUENCE.length - 1) {
    const next = SKILL_SLOT_SEQUENCE[currentIdx + 1]
    handleSkillSlotClick(next.r, next.s)
  } else {
    // Last slot was just filled — clear focus so the next pick goes back to
    // the auto-target flow instead of being stuck on the final slot.
    clearSkillFocus()
  }
}

const findFirstEmptySkillSlot = () => {
  for (const {r, s} of SKILL_SLOT_SEQUENCE) {
    const role = currentLineup.value[r]
    const slot = s === 1 ? role.skill1 : role.skill2
    if (!slot) return {r, s}
  }
  return null
}

const lineupShakeActive = ref(false)
const triggerLineupShake = () => {
  lineupShakeActive.value = false
  // Force restart the animation by toggling on next frame
  requestAnimationFrame(() => { lineupShakeActive.value = true })
}

const clearSkillFocus = () => {
  currentSelectingSkillRole.value = null
  currentSelectingSkillSlot.value = null
}

const selectSkillFromDialog = (skill: Skill) => {
  // 1. Use focused slot if any.
  // 2. Otherwise auto-target the first empty slot in the standard sequence.
  // 3. If none empty, shake the lineup grid to tell the user to focus a slot.
  const hadFocus = !!currentSelectingSkillRole.value && currentSelectingSkillSlot.value !== null
  let targetRole = currentSelectingSkillRole.value
  let targetSlot = currentSelectingSkillSlot.value as 1 | 2 | null

  if (!hadFocus) {
    const empty = findFirstEmptySkillSlot()
    if (!empty) {
      triggerLineupShake()
      ElMessage.warning('所有戰法欄位都已滿，請先點擊欲覆寫的欄位')
      return
    }
    targetRole = empty.r
    targetSlot = empty.s
  }

  const role = currentLineup.value[targetRole!]
  if (targetSlot === 1) role.skill1 = skill
  if (targetSlot === 2) role.skill2 = skill
  ElMessage.success(`已習得 ${skill.name}`)

  // Only advance focus when the user explicitly focused a slot first.
  // Auto-targeted picks should keep focus cleared so subsequent clicks
  // continue to use the "fill next empty" flow.
  if (hadFocus) {
    currentSelectingSkillRole.value = targetRole
    currentSelectingSkillSlot.value = targetSlot
    advanceFocus()
  }
}

// Conflict detection: 兵種 and 陣法 may only have one active per team.
// Returns the set of skill names that participate in a duplicate group.
const conflictingSkillNames = computed(() => {
  const buckets: Record<string, string[]> = { '兵種': [], '陣法': [] }
  for (const {r, s} of SKILL_SLOT_SEQUENCE) {
    const role = currentLineup.value[r]
    const skill = s === 1 ? role.skill1 : role.skill2
    if (!skill) continue
    if (skill.type in buckets) buckets[skill.type].push(skill.name)
  }
  const out = new Set<string>()
  for (const names of Object.values(buckets)) {
    if (names.length > 1) names.forEach(n => out.add(n))
  }
  return out
})

const resetDialogVisible = ref(false)
const openResetDialog = () => {
  resetDialogVisible.value = true
}

const clearLineup = (type: 'all' | 'current' | 'inventory') => {
  if (type === 'current') {
    clearLineupData('current')
    ElMessage.info('當前隊伍已重置')
  }
  if (type === 'all') {
    clearLineupData('all')
    clearInventory()
    ElMessage.info('所有資料已重置')
  }
  if (type === 'inventory') {
    clearInventory()
    ElMessage.info('庫存已清空')
  }
  history.replaceState(null, '', window.location.pathname)
  resetDialogVisible.value = false
}

const shareDialogVisible = ref(false)
const openShareDialog = () => {
  shareDialogVisible.value = true
}

const shareLineup = (type: 'all' | 'current' | 'inventory') => {
  const data: ShareableData = {}
  if (type === 'inventory' || type === 'all') {
    data.inv_h = ownedHeroes.value
    data.inv_s = ownedSkills.value
  }
  if (type === 'current') {
    const l = currentLineup.value
    data.lineups = [{
      name: l.name,
      m: l.main.hero?.name, m_s1: l.main.skill1?.name, m_s2: l.main.skill2?.name, m_st: l.main.stats, m_eq: l.main.equipTraits?.map(t => t ? {n: t.name, r: t.rank, d: t.description} : null), m_bt: l.main.breakthrough,
      v1: l.vice1.hero?.name, v1_s1: l.vice1.skill1?.name, v1_s2: l.vice1.skill2?.name, v1_st: l.vice1.stats, v1_eq: l.vice1.equipTraits?.map(t => t ? {n: t.name, r: t.rank, d: t.description} : null), v1_bt: l.vice1.breakthrough,
      v2: l.vice2.hero?.name, v2_s1: l.vice2.skill1?.name, v2_s2: l.vice2.skill2?.name, v2_st: l.vice2.stats, v2_eq: l.vice2.equipTraits?.map(t => t ? {n: t.name, r: t.rank, d: t.description} : null), v2_bt: l.vice2.breakthrough,
    }]
  }
  if (type === 'all') {
    data.lineups = lineups.map(l => ({
      name: l.name,
      m: l.main.hero?.name, m_s1: l.main.skill1?.name, m_s2: l.main.skill2?.name, m_st: l.main.stats, m_eq: l.main.equipTraits?.map(t => t ? {n: t.name, r: t.rank, d: t.description} : null), m_bt: l.main.breakthrough,
      v1: l.vice1.hero?.name, v1_s1: l.vice1.skill1?.name, v1_s2: l.vice1.skill2?.name, v1_st: l.vice1.stats, v1_eq: l.vice1.equipTraits?.map(t => t ? {n: t.name, r: t.rank, d: t.description} : null), v1_bt: l.vice1.breakthrough,
      v2: l.vice2.hero?.name, v2_s1: l.vice2.skill1?.name, v2_s2: l.vice2.skill2?.name, v2_st: l.vice2.stats, v2_eq: l.vice2.equipTraits?.map(t => t ? {n: t.name, r: t.rank, d: t.description} : null), v2_bt: l.vice2.breakthrough,
    }))
  }
  
  const json = JSON.stringify(data)
  const b64 = btoa(unescape(encodeURIComponent(json)))
  const url = `${window.location.origin}${window.location.pathname}#${b64}`
  
  navigator.clipboard.writeText(url).then(() => {
    ElMessage.success('分享連結已複製到剪貼簿！')
    shareDialogVisible.value = false
  }).catch(() => {
    ElMessage.error('複製失敗，請手動複製網址')
  })
}

const { heroes, skills } = useData()

const initFromHash = () => {
  if (window.location.hash) {
    try {
      const b64 = window.location.hash.slice(1)
      const json = decodeURIComponent(escape(atob(b64)))
      const data = JSON.parse(json) as ShareableData
            if (data.inventory) ownedHeroes.value = data.inventory
            if (data.inv_h) ownedHeroes.value = data.inv_h
            if (data.inv_s) ownedSkills.value = data.inv_s
            
            // Auto-activate "Owned Only" filter if inventory data exists
            if ((data.inv_h && data.inv_h.length > 0) || (data.inv_s && data.inv_s.length > 0) || (data.inventory && data.inventory.length > 0)) {
              showOwnedOnly.value = true
            }
            
            if (data.lineups && Array.isArray(data.lineups)) {
        data.lineups.forEach((l, i) => {
          if (i >= 5) return
          const target = lineups[i]
          if (l.name) target.name = l.name
          const restore = (prefix: string, role: RoleData) => {
            const safeL = l as any
            const hName = safeL[prefix]
            if (hName) role.hero = heroes.value.find(h => h.name === hName) || null
            const s1Name = safeL[prefix + '_s1']
            if (s1Name) role.skill1 = skills.value.find(s => s.name === s1Name || s.name_jp === s1Name) || null
            const s2Name = safeL[prefix + '_s2']
            if (s2Name) role.skill2 = skills.value.find(s => s.name === s2Name || s.name_jp === s2Name) || null
            if (safeL[prefix + '_st']) role.stats = safeL[prefix + '_st']
            if (safeL[prefix + '_eq']) {
              role.equipTraits = safeL[prefix + '_eq'].map((t: any) => t ? { name: t.n, rank: t.r, description: t.d, active: true } : null)
            }
            const bt = safeL[prefix + '_bt']
            if (typeof bt === 'number') role.breakthrough = Math.max(0, Math.min(5, bt))
          }
          restore('m', target.main)
          restore('v1', target.vice1)
          restore('v2', target.vice2)
        })
      }
      ElMessage.success('已載入分享的配置')
      history.replaceState(null, '', window.location.pathname)
    } catch (e) {
      ElMessage.error('無效的分享連結')
    }
  }
}

onMounted(() => {
  setTimeout(initFromHash, 100)
})
</script>

<style>
body {
  margin: 0;
  overflow: hidden; 
}
.el-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.el-tabs__content {
  flex: 1;
  overflow: hidden; 
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.el-tab-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.skill-select-dialog .el-dialog__body {
  padding: 10px 20px 20px;
  overflow: hidden;
}
@keyframes lineup-shake {
  0%, 100% { transform: translateX(0); }
  20%      { transform: translateX(-6px); }
  40%      { transform: translateX(6px); }
  60%      { transform: translateX(-4px); }
  80%      { transform: translateX(4px); }
}
.lineup-shake {
  animation: lineup-shake 0.4s ease-in-out;
}
</style>