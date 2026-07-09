import { defineStore } from 'pinia'

/**
 * Markers Store — Server-persisted map markers with auto-tagging (v2.0).
 *
 * Manages:
 * - markers: all saved markers (synced from backend)
 * - searchQuery / selectedTags: client-side filtering state
 * - isLoading / error: loading state
 *
 * Backend API: /map/markers (GET, POST, PUT, DELETE)
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

const API_BASE = import.meta.env.VITE_API_URL || '/fde-api'

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
    /** Fetch all markers from the backend */
    async fetchMarkers() {
      this.isLoading = true
      this.error = ''
      try {
        const resp = await fetch(`${API_BASE}/map/markers`)
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
      try {
        const resp = await fetch(`${API_BASE}/map/markers/tags`)
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
      try {
        const resp = await fetch(`${API_BASE}/map/markers`, {
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
      try {
        const resp = await fetch(`${API_BASE}/map/markers/${id}`, {
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
      try {
        const resp = await fetch(`${API_BASE}/map/markers/${id}`, {
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
