<template>
  <el-container class="w-full bg-slate-50" style="height: 100dvh">
    <el-header class="app-header bg-white border-b border-gray-200 flex items-center justify-between px-0 md:px-4 sticky top-0 z-50">
      <div class="flex items-center gap-1 md:gap-4">
        <!-- Mobile Menu Button -->
        <el-button class="md:hidden !px-1 !mr-0" text @click="mobileSidebarVisible = true">
          <el-icon :size="20"><Menu /></el-icon>
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

      <div class="flex items-center gap-1 md:gap-0 pr-1 md:pr-0">
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

          <!-- Auth: login button when logged out, branded user pill when logged in -->
          <template v-if="!isLoggedIn">
            <el-button text @click="authDialogVisible = true" class="hidden sm:inline-flex !ml-1">
              <el-icon class="mr-1"><User /></el-icon> 登入
            </el-button>
            <el-button text @click="authDialogVisible = true" class="sm:hidden !px-2">
              <el-icon><User /></el-icon>
            </el-button>
          </template>
          <el-dropdown v-else trigger="click" @command="onUserMenu" placement="bottom-end">
            <button class="user-pill">
              <span class="user-pill-dot" />
              <el-icon><User /></el-icon>
              <span class="hidden sm:inline truncate max-w-[120px]">{{ displayName }}</span>
              <el-icon class="opacity-70"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu class="min-w-[180px]">
                <el-dropdown-item command="my-shares">
                  <el-icon class="mr-1"><Share /></el-icon> 我的分享
                </el-dropdown-item>
                <el-dropdown-item command="rename">
                  <el-icon class="mr-1"><Edit /></el-icon> 編輯名稱
                </el-dropdown-item>
                <el-dropdown-item command="signout" divided>
                  <el-icon class="mr-1"><Close /></el-icon> 登出
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
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

    <el-main class="app-main p-0 overflow-hidden">
      
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
                            v-model:bingxue="currentLineup.main.bingxue"
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
                            v-model:bingxue="currentLineup.vice1.bingxue"
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
                            v-model:bingxue="currentLineup.vice2.bingxue"
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
        
                                      <div class="flex-1 md:flex-none md:h-full w-full md:w-[45%] bg-white border-t md:border-t-0 md:border-l border-gray-200 flex flex-col shadow-xl z-40 min-h-0">
        
                                        <el-tabs v-model="activeTab" class="library-tabs flex-1 flex flex-col px-0 pt-0 md:px-4 md:pt-2" stretch>                                <el-tab-pane label="武將庫" name="heroes" class="h-full flex flex-col overflow-hidden">
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
                <div class="w-full md:container md:mx-auto h-full flex flex-col p-0 md:p-4">
                  <el-tabs v-model="inventoryActiveTab" class="inventory-tabs flex-1 flex flex-col" type="border-card">
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
    <el-dialog v-model="shareDialogVisible" title="分享配置" width="340px" align-center>
      <div class="flex flex-col gap-3">
        <!-- Logged-in users can name shares for the 我的分享 list -->
        <div v-if="isLoggedIn" class="flex flex-col gap-1">
          <el-input
            v-model="shareNameInput"
            maxlength="50"
            placeholder="名稱（可選）"
            clearable
          />
          <p class="text-[11px] text-gray-400 leading-snug">
            此名稱僅顯示於「我的分享」列表，不會出現在分享連結或對方畫面
          </p>
        </div>

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

    <!-- My Shares Dialog -->
    <el-dialog v-model="mySharesDialogVisible" title="我的分享" width="640px" align-center>
      <div v-loading="mySharesLoading" class="min-h-[120px]">
        <p v-if="!mySharesLoading && myShares.length === 0" class="text-center text-gray-400 py-8 text-sm">
          還沒有任何已建立的分享。<br>
          登入狀態下用右上角「分享」建立的連結會自動顯示在這裡。
        </p>
        <el-table v-else-if="myShares.length > 0" :data="sortedMyShares" size="default" style="width: 100%">
          <el-table-column label="" width="44" align="center">
            <template #default="{ row }">
              <button
                @click="togglePinShare(row)"
                :title="row.pinned ? '取消釘選' : '釘選到頂端'"
                class="pin-btn"
                :class="{ 'pin-btn-on': row.pinned }"
              >
                <el-icon><component :is="row.pinned ? StarFilled : Star" /></el-icon>
              </button>
            </template>
          </el-table-column>
          <el-table-column label="名稱" min-width="180">
            <template #default="{ row }">
              <div v-if="editingSlug === row.slug" class="flex items-center gap-1">
                <el-input
                  v-model="editingDraft"
                  size="small"
                  maxlength="50"
                  placeholder="輸入名稱"
                  @keyup.enter="saveShareName(row)"
                  @keyup.esc="cancelEditShareName"
                  autofocus
                />
                <el-button size="small" type="primary" :icon="Check" @click="saveShareName(row)" />
                <el-button size="small" :icon="Close" @click="cancelEditShareName" />
              </div>
              <div v-else class="flex items-center gap-2 group">
                <span :class="row.display_name ? 'text-gray-800' : 'text-gray-400 italic'">
                  {{ row.display_name || '未命名' }}
                </span>
                <el-button
                  text
                  size="small"
                  :icon="Edit"
                  class="opacity-0 group-hover:opacity-100"
                  @click="startEditShareName(row)"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="連結" width="160">
            <template #default="{ row }">
              <button
                @click="copyShareUrl(row.slug)"
                class="text-xs text-indigo-600 hover:text-indigo-800 hover:underline font-mono"
                title="點擊複製分享連結"
              >
                #s/{{ row.slug }}
              </button>
            </template>
          </el-table-column>
          <el-table-column label="更新" width="100">
            <template #default="{ row }">
              <span class="text-xs text-gray-500">{{ relativeTime(row.updated_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="" width="60" align="center">
            <template #default="{ row }">
              <el-popconfirm
                title="確定刪除這個分享？刪除後連結會立刻失效。"
                confirm-button-text="刪除"
                cancel-button-text="取消"
                confirm-button-type="danger"
                @confirm="removeMyShare(row)"
              >
                <template #reference>
                  <el-button text size="small" type="danger" :icon="Delete" />
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <!-- Rename Dialog (first-time prompt + dropdown action) -->
    <el-dialog v-model="renameDialogVisible" title="設定顯示名稱" width="340px" align-center>
      <div class="flex flex-col gap-3 pb-1">
        <p class="text-xs text-gray-500 -mt-1 mb-1">
          這個名稱會顯示在你的分享、未來功能會用到。隨時可從右上角下拉選單再改。
        </p>
        <el-input
          v-model="renameInput"
          maxlength="30"
          show-word-limit
          placeholder="例：張三"
          @keyup.enter="submitRename"
          autofocus
        />
        <el-button
          type="primary"
          :loading="renameSaving"
          @click="submitRename"
          class="w-full !m-0"
        >
          確定
        </el-button>
      </div>
    </el-dialog>

    <!-- Auth Dialog -->
    <el-dialog v-model="authDialogVisible" title="登入帳號" width="340px" align-center>
      <div class="flex flex-col gap-3 pb-1">
        <p class="text-xs text-gray-500 text-center -mt-1 mb-1 leading-relaxed">
          選擇方式登入，將帳號與你建立的分享連結綁定
        </p>
        <!-- Google button: light theme per Google branding guidelines -->
        <button
          @click="onSignIn('google')"
          class="oauth-btn oauth-btn-google"
        >
          <svg class="w-[18px] h-[18px] flex-shrink-0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
            <path fill="#FFC107" d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"/>
            <path fill="#FF3D00" d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"/>
            <path fill="#4CAF50" d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238A11.91 11.91 0 0 1 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"/>
            <path fill="#1976D2" d="M43.611 20.083H42V20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"/>
          </svg>
          <span>使用 Google 帳號繼續</span>
        </button>

        <!-- GitHub button: dark theme matching GitHub's brand -->
        <button
          @click="onSignIn('github')"
          class="oauth-btn oauth-btn-github"
        >
          <svg class="w-[18px] h-[18px] flex-shrink-0 fill-current" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
          </svg>
          <span>使用 GitHub 帳號繼續</span>
        </button>

        <p class="text-xs text-gray-400 text-center mt-3 leading-relaxed">
          登入是選用的；不登入也能完整使用所有功能
        </p>
      </div>
    </el-dialog>

    <el-footer class="bg-white border-t border-gray-200 flex items-center justify-center text-xs text-gray-400 h-8 gap-2">
      <span>聯絡作者: yt.neko.vision@gmail.com</span>
      <span class="opacity-50">|</span>
      <span>Discord: neko.vision</span>
      <span class="opacity-50">|</span>
      <a href="https://forms.gle/mnMAqAzP595ygCrJ9" target="_blank" class="text-blue-400 hover:text-blue-500">翻譯錯誤回報</a>
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
import { Flag, Share, Delete, Edit, Close, Check, Menu, User, ArrowDown, Star, StarFilled } from '@element-plus/icons-vue'
import LineupSlot from './components/LineupSlot.vue'
import SkillDescription from './components/SkillDescription.vue'
import HeroLibrary from './components/HeroLibrary.vue'
import SkillLibrary from './components/SkillLibrary.vue'
import MobileSlotDetail from './components/MobileSlotDetail.vue'

import { useData, Hero, Skill, Trait } from './composables/useData'
import { MOCK_EQUIP_TRAITS, ShareableData, ShareableLineup, ShareableBingxue } from './constants/gameData'
import { useLineups, type RoleData, type BingxueActive } from './composables/useLineups'
import { useTroopLevels } from './composables/useTroopLevels'
import { TROOP_TYPES, TROOP_LABELS } from './constants/traits'
import { useInventory } from './composables/useInventory'
import {
  createShare, loadShare, isShareEnabled,
  listMyShares, renameMyShare, pinMyShare, deleteMyShare, type MyShare,
} from './lib/share'
import { handleAuthCallback, type OAuthProvider } from './lib/auth'
import { useAuth } from './composables/useAuth'

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
  shareNameInput.value = ''
  shareDialogVisible.value = true
}

const serializeBx = (bx?: BingxueActive): ShareableBingxue | undefined =>
  bx?.direction
    ? { d: bx.direction, m: bx.major, n: bx.minors.map(mi => ({ n: mi.name, l: mi.level })) }
    : undefined

// CHT → JP name mapping happens only at share/restore boundary.
// Internal state stays CHT (rest of app filters by CHT name).
const heroToJp = (cht: string | undefined): string | undefined =>
  cht ? (heroes.value.find(h => h.name === cht)?.name_jp ?? cht) : undefined
const skillToJp = (cht: string | undefined): string | undefined =>
  cht ? (skills.value.find(s => s.name === cht)?.name_jp ?? cht) : undefined

// Computed keys widen to `string` in TS, so the explicit Partial cast is the
// honest contract — the runtime field names (`m_s1`, `v1_s1`, etc.) match
// ShareableLineup by convention. Typos in the template literals would silently
// produce ignored fields; the cast at least keeps callers honest about shape.
const serializeRole = (role: RoleData, prefix: 'm' | 'v1' | 'v2'): Partial<ShareableLineup> => ({
  [prefix]: heroToJp(role.hero?.name),
  [`${prefix}_s1`]: skillToJp(role.skill1?.name),
  [`${prefix}_s2`]: skillToJp(role.skill2?.name),
  [`${prefix}_st`]: role.stats,
  [`${prefix}_eq`]: role.equipTraits?.map(t => t ? {n: t.name, r: t.rank, d: t.description} : null),
  [`${prefix}_bt`]: role.breakthrough,
  [`${prefix}_bx`]: serializeBx(role.bingxue),
}) as Partial<ShareableLineup>

const serializeLineup = (l: typeof lineups[number]): ShareableLineup => ({
  name: l.name,
  ...serializeRole(l.main, 'm'),
  ...serializeRole(l.vice1, 'v1'),
  ...serializeRole(l.vice2, 'v2'),
})

// Optional name for the next share — entered in the share dialog when logged
// in. Reset on every dialog open so it doesn't carry over between actions.
const shareNameInput = ref('')

const shareLineup = async (type: 'all' | 'current' | 'inventory') => {
  const data: ShareableData = { v: 2 }
  if (type === 'inventory' || type === 'all') {
    data.inv_h = ownedHeroes.value.map(n => heroToJp(n) ?? n)
    data.inv_s = ownedSkills.value.map(n => skillToJp(n) ?? n)
  }
  if (type === 'current') {
    data.lineups = [serializeLineup(currentLineup.value)]
  }
  if (type === 'all') {
    data.lineups = lineups.map(serializeLineup)
  }

  const origin = `${window.location.origin}${window.location.pathname}`
  const buildLegacyUrl = () => {
    const json = JSON.stringify(data)
    const b64 = btoa(unescape(encodeURIComponent(json)))
    return `${origin}#${b64}`
  }

  // Only logged-in shares can be named — anon shares aren't listed anywhere.
  const displayName = isLoggedIn.value ? shareNameInput.value.trim() : ''

  let url: string
  if (isShareEnabled()) {
    try {
      const slug = await createShare(data, displayName ? { displayName } : undefined)
      url = `${origin}#s/${slug}`
    } catch (e) {
      console.warn('[share] short URL failed, using long URL fallback:', e)
      url = buildLegacyUrl()
    }
  } else {
    url = buildLegacyUrl()
  }

  navigator.clipboard.writeText(url).then(() => {
    ElMessage.success('分享連結已複製到剪貼簿！')
    shareDialogVisible.value = false
    shareNameInput.value = ''
  }).catch(() => {
    ElMessage.error('複製失敗，請手動複製網址')
  })
}

const { heroes, skills } = useData()

// Restore in-memory state from a ShareableData blob (used by share links AND
// by sign-in recovery). Lookups try JP first (v2), CHT second (v1 / legacy).
const restoreFromBlob = (data: ShareableData) => {
  const findHeroByKey = (key: string) => heroes.value.find(h => h.name_jp === key || h.name === key)
  const findSkillByKey = (key: string) => skills.value.find(s => s.name_jp === key || s.name === key)
  const toCht = <T extends { name: string }>(arr: string[], finder: (k: string) => T | undefined): string[] =>
    arr.map(k => finder(k)?.name ?? k)

  if (data.inventory) ownedHeroes.value = toCht(data.inventory, findHeroByKey)
  if (data.inv_h) ownedHeroes.value = toCht(data.inv_h, findHeroByKey)
  if (data.inv_s) ownedSkills.value = toCht(data.inv_s, findSkillByKey)

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
        if (hName) role.hero = findHeroByKey(hName) || null
        const s1Name = safeL[prefix + '_s1']
        if (s1Name) role.skill1 = findSkillByKey(s1Name) || null
        const s2Name = safeL[prefix + '_s2']
        if (s2Name) role.skill2 = findSkillByKey(s2Name) || null
        if (safeL[prefix + '_st']) role.stats = safeL[prefix + '_st']
        if (safeL[prefix + '_eq']) {
          role.equipTraits = safeL[prefix + '_eq'].map((t: any) => t ? { name: t.n, rank: t.r, description: t.d, active: true } : null)
        }
        const bt = safeL[prefix + '_bt']
        if (typeof bt === 'number') role.breakthrough = Math.max(0, Math.min(5, bt))
        const bx = safeL[prefix + '_bx']
        if (bx && bx.d) {
          role.bingxue = {
            direction: bx.d,
            major: bx.m ?? null,
            minors: Array.isArray(bx.n) ? bx.n.map((mi: any) => ({ name: mi.n, level: mi.l })) : [],
          }
        }
      }
      restore('m', target.main)
      restore('v1', target.vice1)
      restore('v2', target.vice2)
    })
  }
}

// Snapshot current state under a recovery key before OAuth full-page redirect,
// so handleAuthCallback's success path can restore the lineup the user was
// building. 5-minute TTL so a stale snapshot from days ago doesn't surprise.
const RECOVERY_KEY = 'nobunaga.auth.recovery'
const RECOVERY_TTL_MS = 5 * 60 * 1000

const snapshotForRecovery = () => {
  const blob: ShareableData = { v: 2 }
  blob.lineups = lineups.map(serializeLineup)
  blob.inv_h = ownedHeroes.value.map(n => heroToJp(n) ?? n)
  blob.inv_s = ownedSkills.value.map(n => skillToJp(n) ?? n)
  localStorage.setItem(RECOVERY_KEY, JSON.stringify({ blob, ts: Date.now() }))
}

const consumeRecovery = (): boolean => {
  const raw = localStorage.getItem(RECOVERY_KEY)
  if (!raw) return false
  localStorage.removeItem(RECOVERY_KEY)
  try {
    const { blob, ts } = JSON.parse(raw) as { blob: ShareableData; ts: number }
    if (Date.now() - ts > RECOVERY_TTL_MS) return false
    restoreFromBlob(blob)
    return true
  } catch {
    return false
  }
}

// --- Auth ---
const {
  user, isLoggedIn, displayName, needsDisplayName,
  signIn, signOut, updateDisplayName, refreshFromStorage,
} = useAuth()
const authDialogVisible = ref(false)
const renameDialogVisible = ref(false)
const renameInput = ref('')
const renameSaving = ref(false)

const onSignIn = (provider: OAuthProvider) => {
  authDialogVisible.value = false
  snapshotForRecovery()
  signIn(provider)  // full-page redirect — nothing after this runs
}

const onUserMenu = async (cmd: string) => {
  if (cmd === 'signout') {
    await signOut()
    ElMessage.success('已登出')
  } else if (cmd === 'rename') {
    openRenameDialog()
  } else if (cmd === 'my-shares') {
    openMySharesDialog()
  }
}

// --- My Shares ---
const mySharesDialogVisible = ref(false)
const mySharesLoading = ref(false)
const myShares = ref<MyShare[]>([])
// Inline rename: track which row (slug) is editing + the draft value.
const editingSlug = ref<string | null>(null)
const editingDraft = ref('')

const openMySharesDialog = async () => {
  mySharesDialogVisible.value = true
  mySharesLoading.value = true
  try {
    myShares.value = await listMyShares()
  } catch (e) {
    ElMessage.error(`載入失敗：${(e as Error).message}`)
  } finally {
    mySharesLoading.value = false
  }
}

const startEditShareName = (s: MyShare) => {
  editingSlug.value = s.slug
  editingDraft.value = s.display_name ?? ''
}

const cancelEditShareName = () => {
  editingSlug.value = null
  editingDraft.value = ''
}

const saveShareName = async (s: MyShare) => {
  const next = editingDraft.value.trim()
  if (next === (s.display_name ?? '').trim()) {
    cancelEditShareName()
    return
  }
  try {
    await renameMyShare(s.slug, next || null)
    s.display_name = next || null
    s.updated_at = new Date().toISOString()
    cancelEditShareName()
    ElMessage.success('已更新')
  } catch (e) {
    ElMessage.error(`更新失敗：${(e as Error).message}`)
  }
}

const removeMyShare = async (s: MyShare) => {
  try {
    await deleteMyShare(s.slug)
    myShares.value = myShares.value.filter(x => x.slug !== s.slug)
    ElMessage.success('已刪除')
  } catch (e) {
    ElMessage.error(`刪除失敗：${(e as Error).message}`)
  }
}

const togglePinShare = async (s: MyShare) => {
  const next = !s.pinned
  try {
    await pinMyShare(s.slug, next)
    s.pinned = next  // mutate in place; sortedMyShares is a computed off myShares
    s.updated_at = new Date().toISOString()
  } catch (e) {
    ElMessage.error(`${next ? '釘選' : '取消釘選'}失敗：${(e as Error).message}`)
  }
}

// Sort: pinned first, then named (alphabetical), then unnamed (newest first).
const sortedMyShares = computed(() => {
  return [...myShares.value].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    const aName = a.display_name?.trim() ?? ''
    const bName = b.display_name?.trim() ?? ''
    if (!!aName !== !!bName) return aName ? -1 : 1
    if (aName && bName) {
      const cmp = aName.localeCompare(bName, 'zh-Hant')
      if (cmp !== 0) return cmp
    }
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

const copyShareUrl = (slug: string) => {
  const url = `${window.location.origin}${window.location.pathname}#s/${slug}`
  navigator.clipboard.writeText(url).then(() => {
    ElMessage.success('連結已複製')
  }).catch(() => {
    ElMessage.error('複製失敗')
  })
}

// "5 分鐘前" / "2 天前" relative-time, no Intl dependency.
const relativeTime = (iso: string): string => {
  const sec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (sec < 60) return '剛剛'
  if (sec < 3600) return `${Math.floor(sec / 60)} 分鐘前`
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小時前`
  if (sec < 86400 * 30) return `${Math.floor(sec / 86400)} 天前`
  return new Date(iso).toLocaleDateString('zh-Hant')
}

const openRenameDialog = () => {
  renameInput.value = displayName.value
  renameDialogVisible.value = true
}

const submitRename = async () => {
  const name = renameInput.value.trim()
  if (!name) {
    ElMessage.warning('名稱不可為空')
    return
  }
  renameSaving.value = true
  try {
    await updateDisplayName(name)
    renameDialogVisible.value = false
    ElMessage.success('名稱已更新')
  } catch (e) {
    ElMessage.error(`更新失敗：${(e as Error).message}`)
  } finally {
    renameSaving.value = false
  }
}

const initFromHash = async () => {
  // 1. OAuth callback first — must consume the auth hash before share-loading.
  try {
    if (handleAuthCallback()) {
      refreshFromStorage()
      const recovered = consumeRecovery()
      ElMessage.success(recovered ? '登入成功，已還原配置' : '登入成功')
      // First-time prompt: ask new users to pick a display name.
      if (needsDisplayName.value) {
        renameInput.value = displayName.value  // prefill with email prefix
        renameDialogVisible.value = true
      }
      return
    }
  } catch (e) {
    ElMessage.error(`登入失敗：${(e as Error).message}`)
    return
  }

  // 2. Share link (slug or legacy base64).
  if (window.location.hash) {
    try {
      const hash = window.location.hash.slice(1)
      let data: ShareableData
      if (hash.startsWith('s/')) {
        data = (await loadShare(hash.slice(2))) as ShareableData
      } else {
        const json = decodeURIComponent(escape(atob(hash)))
        data = JSON.parse(json) as ShareableData
      }
      restoreFromBlob(data)
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
/* Element Plus' lock-scroll adds `width: calc(100% - <scrollbarWidth>)`
   (and sometimes padding-right) to body when a modal/drawer mask opens,
   to compensate for the disappearing scrollbar. But our body is already
   `overflow: hidden` so there is no scrollbar to compensate for — the
   shrunk width just makes the content scale down from the top-left and
   leaves a white stripe on the right/bottom. Neutralize all of them. */
body.el-popup-parent--hidden,
html.el-popup-parent--hidden {
  width: 100% !important;
  padding-right: 0 !important;
  padding-bottom: 0 !important;
  overflow: hidden !important;
}
/* Mobile: compact header (height 50px, no horizontal padding). */
.app-header {
  --el-header-height: 60px;
  height: var(--el-header-height);
}
.app-main {
  height: calc(100dvh - var(--el-header-height) - 32px);
}
@media (max-width: 767px) {
  .app-header {
    --el-header-height: 50px;
  }
  /* Tighten Element Plus button default margin between siblings on mobile. */
  .app-header .el-button + .el-button {
    margin-left: 4px;
  }
}
/* Tighten the gap between the 武將庫/戰法庫 tab header and its panel content.
   Element Plus default is margin: 0 0 15px; which leaves too much dead space. */
.el-tabs--top > .el-tabs__header.is-top {
  margin-bottom: 6px;
}
@media (max-width: 767px) {
  .el-tabs--top > .el-tabs__header.is-top {
    margin-bottom: 2px;
  }
}
/* Library tabs (武將庫/戰法庫): shorter header row (80% of EP default 40px). */
.library-tabs .el-tabs__item {
  height: 32px;
  line-height: 32px;
}
.library-tabs .el-tabs__nav-wrap::after {
  height: 1px;
}
/* Inventory editor (庫存編輯) — tighten the border-card tab panel.
   Default .el-tabs--border-card content padding is 15px; shrink on mobile
   and trim the header row to match the 80% rule used elsewhere. */
.inventory-tabs.el-tabs--border-card > .el-tabs__header .el-tabs__item {
  height: 32px;
  line-height: 32px;
}
@media (max-width: 767px) {
  .inventory-tabs.el-tabs--border-card {
    border: 0;
    box-shadow: none;
  }
  .inventory-tabs.el-tabs--border-card > .el-tabs__content {
    padding: 0;
  }
  .inventory-tabs.el-tabs--border-card > .el-tabs__header {
    margin-bottom: 0;
  }
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

/* OAuth provider buttons — branded styling per provider guidelines */
.oauth-btn {
  width: 100%;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
  border: 1px solid transparent;
}
.oauth-btn:focus-visible {
  outline: 2px solid #6366f1;
  outline-offset: 2px;
}
.oauth-btn-google {
  background: #ffffff;
  color: #1f1f1f;
  border-color: #dadce0;
}
.oauth-btn-google:hover {
  background: #f8f9fa;
  border-color: #c4c6c9;
  box-shadow: 0 1px 2px rgba(60, 64, 67, 0.08);
}
.oauth-btn-google:active {
  background: #f1f3f4;
}
.oauth-btn-github {
  background: #24292f;
  color: #ffffff;
  border-color: #24292f;
}
.oauth-btn-github:hover {
  background: #32383f;
  border-color: #32383f;
}
.oauth-btn-github:active {
  background: #1c2128;
}

/* Logged-in pill — visually distinct from the plain "登入" text button.
   Height matches el-button default (32px) so it lines up with 重置 etc. */
.user-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px 0 10px;
  margin-left: 4px;
  border-radius: 999px;
  background: #eef2ff;        /* indigo-50 */
  border: 1px solid #c7d2fe;  /* indigo-200 */
  color: #4338ca;             /* indigo-700 */
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
  line-height: 1;
  box-sizing: border-box;
}
.user-pill:hover {
  background: #e0e7ff;        /* indigo-100 */
  border-color: #a5b4fc;      /* indigo-300 */
}
.user-pill:focus-visible {
  outline: 2px solid #6366f1;
  outline-offset: 2px;
}
.user-pill-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #22c55e;        /* green-500 — "online/active" indicator */
  box-shadow: 0 0 0 2px #dcfce7;
}

/* Pin star button in 我的分享 table — subtle when off, gold when on */
.pin-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: #cbd5e1;             /* slate-300 */
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.pin-btn:hover {
  background: #f1f5f9;        /* slate-100 */
  color: #94a3b8;             /* slate-400 */
}
.pin-btn-on,
.pin-btn-on:hover {
  color: #f59e0b;             /* amber-500 */
}
.pin-btn-on:hover {
  background: #fef3c7;        /* amber-100 */
}
</style>