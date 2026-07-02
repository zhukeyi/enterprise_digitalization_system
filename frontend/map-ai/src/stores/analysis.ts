import { defineStore } from 'pinia'

/**
 * Analysis Store — Global state for marked entities and analysis state (M3-T8).
 *
 * Manages:
 * - markedEntities: entities selected by the user for correlation analysis
 * - isAnalysisBoxOpen: whether the analysis floating box is visible
 * - toastMessages: ephemeral UI feedback messages
 *
 * Persistence: markedEntities are saved to localStorage on every mutation.
 */

export interface MarkedEntity {
  id: string
  name: string
  type: string
  lng?: number
  lat?: number
  metadata?: Record<string, unknown>
  markedAt: number
}

export interface ToastMessage {
  id: string
  text: string
  type: 'info' | 'success' | 'warning' | 'error'
  duration: number
}

const STORAGE_KEY = 'fde_marked_entities'
const MAX_ENTITIES = 20

function loadFromStorage(): MarkedEntity[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (e: unknown): e is MarkedEntity =>
        typeof e === 'object' && e !== null && 'id' in e && 'name' in e,
    )
  } catch {
    return []
  }
}

function saveToStorage(entities: MarkedEntity[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entities))
  } catch {
    // localStorage might be unavailable (private mode, quota exceeded)
  }
}

export const useAnalysisStore = defineStore('analysis', {
  state: () => ({
    /** Entities marked for correlation analysis */
    markedEntities: loadFromStorage() as MarkedEntity[],
    /** Whether the analysis floating box is visible */
    isAnalysisBoxOpen: false,
    /** Whether an analysis request is in flight */
    isAnalyzing: false,
    /** Ephemeral toast messages for UI feedback */
    toastMessages: [] as ToastMessage[],
    /** Last analysis result (for caching) */
    lastAnalysisResult: null as Record<string, unknown> | null,
  }),

  getters: {
    /** Count of marked entities */
    entityCount: (state) => state.markedEntities.length,
    /** Whether we have enough entities for analysis (minimum 2) */
    canAnalyze: (state) => state.markedEntities.length >= 2,
    /** Get entity IDs as a list */
    entityIds: (state) => state.markedEntities.map((e) => e.id),
    /** Check if an entity is already marked */
    isMarked: (state) => (id: string) => state.markedEntities.some((e) => e.id === id),
  },

  actions: {
    /** Add an entity to the marked list. Prevents duplicates. */
    addEntity(entity: Omit<MarkedEntity, 'markedAt'>) {
      if (this.isMarked(entity.id)) {
        this.addToast('该实体已添加', 'warning')
        return false
      }
      if (this.markedEntities.length >= MAX_ENTITIES) {
        this.addToast(`最多只能添加 ${MAX_ENTITIES} 个实体`, 'warning')
        return false
      }
      this.markedEntities.push({
        ...entity,
        markedAt: Date.now(),
      })
      saveToStorage(this.markedEntities)
      this.addToast(`已添加 "${entity.name}"`, 'success')
      this.isAnalysisBoxOpen = true
      return true
    },

    /** Remove an entity by ID */
    removeEntity(id: string) {
      const idx = this.markedEntities.findIndex((e) => e.id === id)
      if (idx === -1) return false
      const entity = this.markedEntities[idx]
      this.markedEntities.splice(idx, 1)
      saveToStorage(this.markedEntities)
      this.addToast(`已移除 "${entity.name}"`, 'info')
      return true
    },

    /** Remove all marked entities */
    clearAll() {
      if (this.markedEntities.length === 0) return
      this.markedEntities = []
      saveToStorage(this.markedEntities)
      this.addToast('已清空所有标记实体', 'info')
    },

    /** Reorder entities (for drag-and-drop sorting) */
    reorderEntities(newOrder: MarkedEntity[]) {
      this.markedEntities = newOrder
      saveToStorage(this.markedEntities)
    },

    /** Open the analysis box */
    openAnalysisBox() {
      this.isAnalysisBoxOpen = true
    },

    /** Close the analysis box */
    closeAnalysisBox() {
      this.isAnalysisBoxOpen = false
    },

    /** Toggle the analysis box visibility */
    toggleAnalysisBox() {
      this.isAnalysisBoxOpen = !this.isAnalysisBoxOpen
    },

    /** Set analyzing state */
    setAnalyzing(value: boolean) {
      this.isAnalyzing = value
    },

    /** Store the last analysis result */
    setAnalysisResult(result: Record<string, unknown>) {
      this.lastAnalysisResult = result
    },

    /** Add a toast message that auto-dismisses */
    addToast(
      text: string,
      type: ToastMessage['type'] = 'info',
      duration = 3000,
    ) {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
      this.toastMessages.push({ id, text, type, duration })
      // Auto-remove after duration
      setTimeout(() => {
        this.removeToast(id)
      }, duration)
    },

    /** Remove a toast message by ID */
    removeToast(id: string) {
      const idx = this.toastMessages.findIndex((t) => t.id === id)
      if (idx !== -1) {
        this.toastMessages.splice(idx, 1)
      }
    },
  },
})
