<script setup lang="ts">
/**
 * ResourcePanel — Left-side floating panel for persisted markers (v2.0).
 *
 * Features:
 * - Search box (instant client-side filtering by name/note/tag)
 * - Tag filter chips (clickable toggle)
 * - Marker list with tags + truncated note
 * - Click marker → flyTo on map
 * - Edit note → modal dialog
 * - Delete marker
 * - Minimize/expand toggle
 */
import { ref, onMounted } from 'vue'
import { useMarkersStore } from '../stores/markers'

const emit = defineEmits<{
  'fly-to': [lng: number, lat: number]
}>()

const store = useMarkersStore()
const isMinimized = ref(false)

// Edit modal state
const editingMarker = ref<string | null>(null)
const editName = ref('')
const editNote = ref('')

function toggleMinimize() {
  isMinimized.value = !isMinimized.value
}

function handleMarkerClick(lng: number, lat: number) {
  emit('fly-to', lng, lat)
}

function startEdit(marker: { id: string; name: string; note: string }) {
  editingMarker.value = marker.id
  editName.value = marker.name
  editNote.value = marker.note
}

function cancelEdit() {
  editingMarker.value = null
}

async function saveEdit() {
  if (!editingMarker.value) return
  await store.updateMarker(editingMarker.value, {
    name: editName.value,
    note: editNote.value,
  })
  editingMarker.value = null
}

async function handleDelete(id: string) {
  await store.deleteMarker(id)
}

onMounted(() => {
  store.fetchMarkers()
  store.fetchTags()
})
</script>

<template>
  <div class="resource-panel" :class="{ minimized: isMinimized }">
    <!-- Header -->
    <div class="panel-header" @click="toggleMinimize">
      <div class="header-left">
        <span class="header-icon">🔖</span>
        <span class="header-title">点位资源</span>
        <span class="count-badge">{{ store.markerCount }}</span>
      </div>
      <button class="minimize-btn" title="最小化">
        {{ isMinimized ? '▲' : '▼' }}
      </button>
    </div>

    <!-- Body -->
    <div v-if="!isMinimized" class="panel-body">
      <!-- Search -->
      <div class="search-box">
        <input
          v-model="store.searchQuery"
          type="text"
          placeholder="搜索点位或标签..."
          class="search-input"
        />
        <button
          v-if="store.hasActiveFilters"
          class="clear-filters-btn"
          @click="store.clearFilters()"
        >
          清除
        </button>
      </div>

      <!-- Tag filters -->
      <div v-if="store.allTags.length > 0" class="tag-filters">
        <span
          v-for="tagInfo in store.allTags"
          :key="tagInfo.tag"
          class="tag-chip"
          :class="{ active: store.selectedTags.includes(tagInfo.tag) }"
          @click="store.toggleTagFilter(tagInfo.tag)"
        >
          {{ tagInfo.tag }} ×{{ tagInfo.count }}
        </span>
      </div>

      <!-- Loading -->
      <div v-if="store.isLoading" class="loading-state">
        <span class="loading-spinner" />
        加载中...
      </div>

      <!-- Error -->
      <div v-else-if="store.error" class="error-state">
        ⚠️ {{ store.error }}
      </div>

      <!-- Empty -->
      <div v-else-if="store.filteredMarkers.length === 0" class="empty-state">
        <span class="empty-icon">📌</span>
        <p v-if="store.markerCount === 0">
          点击地图标注点位<br />备注将自动生成标签
        </p>
        <p v-else>没有匹配的点位</p>
      </div>

      <!-- Marker list -->
      <div v-else class="marker-list">
        <div
          v-for="marker in store.filteredMarkers"
          :key="marker.id"
          class="marker-item"
          :class="{ editing: editingMarker === marker.id }"
        >
          <!-- Normal view -->
          <template v-if="editingMarker !== marker.id">
            <div class="marker-row" @click="handleMarkerClick(marker.lng, marker.lat)">
              <span class="marker-icon">📍</span>
              <span class="marker-name">{{ marker.name }}</span>
              <div class="marker-actions">
                <button class="action-btn edit-btn" title="编辑" @click.stop="startEdit(marker)">
                  ✏️
                </button>
                <button class="action-btn delete-btn" title="删除" @click.stop="handleDelete(marker.id)">
                  🗑️
                </button>
              </div>
            </div>
            <div v-if="marker.tags.length > 0" class="marker-tags">
              <span v-for="tag in marker.tags" :key="tag" class="marker-tag">{{ tag }}</span>
            </div>
            <div v-if="marker.note" class="marker-note">
              {{ marker.note.length > 50 ? marker.note.slice(0, 50) + '...' : marker.note }}
            </div>
          </template>

          <!-- Edit view -->
          <template v-else>
            <div class="edit-form">
              <input v-model="editName" class="edit-input" placeholder="名称" />
              <textarea
                v-model="editNote"
                class="edit-textarea"
                placeholder="备注（将自动生成标签）"
                rows="3"
              />
              <div class="edit-actions">
                <button class="save-btn" @click="saveEdit">保存</button>
                <button class="cancel-btn" @click="cancelEdit">取消</button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.resource-panel {
  position: fixed;
  top: 108px;
  left: 12px;
  width: 300px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  z-index: 9000;
  overflow: hidden;
  transition: all 0.3s ease;
  max-height: calc(100vh - 128px);
  display: flex;
  flex-direction: column;
}

.resource-panel.minimized {
  width: 200px;
  max-height: 48px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: linear-gradient(135deg, #1a73e8, #4285f4);
  color: white;
  cursor: pointer;
  user-select: none;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  font-size: 16px;
}

.header-title {
  font-size: 14px;
  font-weight: 600;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: rgba(255, 255, 255, 0.25);
  border-radius: 10px;
  font-size: 12px;
  font-weight: bold;
}

.minimize-btn {
  border: none;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 12px;
}

.panel-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  overflow-y: auto;
  flex: 1;
}

/* Search */
.search-box {
  display: flex;
  gap: 6px;
}

.search-input {
  flex: 1;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  outline: none;
  background: #f5f7fa;
  transition: border-color 0.2s;
}

.search-input:focus {
  border-color: #1a73e8;
  background: white;
}

.clear-filters-btn {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0 10px;
  background: white;
  color: #666;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.clear-filters-btn:hover {
  background: #f5f7fa;
}

/* Tag filters */
.tag-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 12px;
  background: #f0f4f8;
  color: #4a5568;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.tag-chip:hover {
  background: #e2e8f0;
}

.tag-chip.active {
  background: #1a73e8;
  color: white;
}

/* States */
.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  text-align: center;
  color: #999;
  font-size: 13px;
  gap: 8px;
}

.empty-icon {
  font-size: 28px;
  opacity: 0.5;
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(26, 115, 232, 0.2);
  border-top-color: #1a73e8;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Marker list */
.marker-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.marker-item {
  background: white;
  border-radius: 8px;
  padding: 8px 10px;
  border: 1px solid #f0f0f0;
  transition: border-color 0.2s;
}

.marker-item:hover {
  border-color: #1a73e8;
}

.marker-item.editing {
  border-color: #1a73e8;
  background: #f8faff;
}

.marker-row {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.marker-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.marker-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: #2d3748;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.marker-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.2s;
}

.marker-item:hover .marker-actions {
  opacity: 1;
}

.action-btn {
  border: none;
  background: none;
  cursor: pointer;
  padding: 2px 4px;
  font-size: 12px;
  border-radius: 4px;
  transition: background 0.2s;
}

.action-btn:hover {
  background: #f0f4f8;
}

.marker-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 4px;
}

.marker-tag {
  background: #e8f0fe;
  color: #1a73e8;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
}

.marker-note {
  font-size: 11px;
  color: #999;
  margin-top: 3px;
  line-height: 1.4;
}

/* Edit form */
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.edit-input {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  outline: none;
}

.edit-input:focus {
  border-color: #1a73e8;
}

.edit-textarea {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  outline: none;
  resize: vertical;
  font-family: inherit;
}

.edit-textarea:focus {
  border-color: #1a73e8;
}

.edit-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.save-btn {
  background: #1a73e8;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
}

.save-btn:hover {
  background: #1557b0;
}

.cancel-btn {
  background: #eee;
  color: #666;
  border: none;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
}

.cancel-btn:hover {
  background: #ddd;
}
</style>
