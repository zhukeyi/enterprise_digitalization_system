import { defineStore } from 'pinia'
import { getRuntimeConfig, getApiBase } from '../mapai/runtime'

/**
 * Markers Store — Server-persisted map markers with auto-tagging (v2.0).
 *
 * Manages:
 * - markers: all saved markers (synced from backend OR injected statically)
 * - searchQuery / selectedTags: client-side filtering state
 * - isLoading / error: loading state
 *
 * Backend API: /map/markers (GET, POST, PUT, DELETE)
 * 嵌入（即插即用）模式下 markersBackend=false，则完全本地化，不请求后端。
 */

export interface MarkerData {
  id: string
  name: string
  lng: number
  lat: number
  note: string
  tags: string[]
  created_at: string
  updated_at: string
}

export interface TagInfo {
  tag: string
  count: number
}

export const useMarkersStore = defineStore('markers', {
  state: () => ({
    markers: [] as MarkerData[],
    allTags: [] as TagInfo[],
    searchQuery: '',
    selectedTags: [] as string[],
    isLoading: false,
    error: '' as string,
  }),

  getters: {
    /** Filtered markers based on search query and selected tags */
    filteredMarkers(state): MarkerData[] {
      let result = state.markers

      // Tag filter
      if (state.selectedTags.length > 0) {
        result = result.filter((m) =>
          state.selectedTags.every((tag) => m.tags.includes(tag)),
        )
      }

      // Search filter (name + note)
      if (state.searchQuery.trim()) {
        const q = state.searchQuery.toLowerCase()
        result = result.filter(
          (m) =>
            m.name.toLowerCase().includes(q) ||
            m.note.toLowerCase().includes(q) ||
            m.tags.some((t) => t.toLowerCase().includes(q)),
        )
      }

      return result
    },

    /** Total marker count */
    markerCount(state): number {
      return state.markers.length
    },

    /** Whether any filters are active */
    hasActiveFilters(state): boolean {
      return state.searchQuery.trim() !== '' || state.selectedTags.length > 0
    },
  },

  actions: {
    /** 是否连接后端（嵌入静态数据模式下为 false） */
    get backendEnabled(): boolean {
      return getRuntimeConfig().markersBackend
    },

    /** 用外部数据一次性播种点位（静态/远端数据源） */
    seedMarkers(list: Array<Partial<MarkerData> & { id: string; name: string; lng: number; lat: number }>) {
      this.markers = list.map((m) => ({
        id: m.id,
        name: m.name,
        lng: m.lng,
        lat: m.lat,
        note: m.note ?? '',
        tags: m.tags ?? [],
        created_at: m.created_at ?? new Date().toISOString(),
        updated_at: m.updated_at ?? new Date().toISOString(),
      }))
      this.recomputeTags()
    },

    /** 仅由本地 markers 重新计算标签计数 */
    recomputeTags() {
      const counter = new Map<string, number>()
      for (const m of this.markers) {
        for (const t of m.tags) counter.set(t, (counter.get(t) || 0) + 1)
      }
      this.allTags = Array.from(counter.entries()).map(([tag, count]) => ({ tag, count }))
    },

    /** Fetch all markers from the backend (静态模式跳过) */
    async fetchMarkers() {
      if (!this.backendEnabled) return
      this.isLoading = true
      this.error = ''
      try {
        const resp = await fetch(`${getApiBase()}/map/markers`)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        this.markers = await resp.json()
      } catch (err: any) {
        this.error = err.message || 'Failed to fetch markers'
        console.error('[markersStore] fetchMarkers:', err)
      } finally {
        this.isLoading = false
      }
    },

    /** Fetch all tags with counts */
    async fetchTags() {
      if (!this.backendEnabled) {
        this.recomputeTags()
        return
      }
      try {
        const resp = await fetch(`${getApiBase()}/map/markers/tags`)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        this.allTags = await resp.json()
      } catch (err: any) {
        console.error('[markersStore] fetchTags:', err)
      }
    },

    /** Create a new marker */
    async createMarker(data: {
      name: string
      lng: number
      lat: number
      note?: string
    }): Promise<MarkerData | null> {
      if (!this.backendEnabled) {
        const marker: MarkerData = {
          id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          name: data.name,
          lng: data.lng,
          lat: data.lat,
          note: data.note ?? '',
          tags: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }
        this.markers.push(marker)
        this.recomputeTags()
        return marker
      }
      try {
        const resp = await fetch(`${getApiBase()}/map/markers`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const marker = await resp.json()
        this.markers.push(marker)
        await this.fetchTags()
        return marker
      } catch (err: any) {
        this.error = err.message || 'Failed to create marker'
        console.error('[markersStore] createMarker:', err)
        return null
      }
    },

    /** Update an existing marker */
    async updateMarker(
      id: string,
      data: { name?: string; note?: string },
    ): Promise<MarkerData | null> {
      if (!this.backendEnabled) {
        const idx = this.markers.findIndex((m) => m.id === id)
        if (idx === -1) return null
        this.markers[idx] = {
          ...this.markers[idx],
          ...data,
          updated_at: new Date().toISOString(),
        }
        this.recomputeTags()
        return this.markers[idx]
      }
      try {
        const resp = await fetch(`${getApiBase()}/map/markers/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const updated = await resp.json()
        const idx = this.markers.findIndex((m) => m.id === id)
        if (idx !== -1) this.markers[idx] = updated
        await this.fetchTags()
        return updated
      } catch (err: any) {
        this.error = err.message || 'Failed to update marker'
        console.error('[markersStore] updateMarker:', err)
        return null
      }
    },

    /** Delete a marker by ID */
    async deleteMarker(id: string): Promise<boolean> {
      if (!this.backendEnabled) {
        this.markers = this.markers.filter((m) => m.id !== id)
        this.recomputeTags()
        return true
      }
      try {
        const resp = await fetch(`${getApiBase()}/map/markers/${id}`, {
          method: 'DELETE',
        })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        this.markers = this.markers.filter((m) => m.id !== id)
        await this.fetchTags()
        return true
      } catch (err: any) {
        this.error = err.message || 'Failed to delete marker'
        console.error('[markersStore] deleteMarker:', err)
        return false
      }
    },

    /** Set search query */
    setSearchQuery(query: string) {
      this.searchQuery = query
    },

    /** Toggle a tag filter */
    toggleTagFilter(tag: string) {
      const idx = this.selectedTags.indexOf(tag)
      if (idx === -1) {
        this.selectedTags.push(tag)
      } else {
        this.selectedTags.splice(idx, 1)
      }
    },

    /** Clear all filters */
    clearFilters() {
      this.searchQuery = ''
      this.selectedTags = []
    },
  },
})
