import { defineStore } from 'pinia'

export interface ChatMessage {
  id: string
  role: 'user' | 'agent'
  content: string
  timestamp: number
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [] as ChatMessage[],
    loading: false,
    _simulateTimeoutId: null as ReturnType<typeof setTimeout> | null,
  }),
  actions: {
    addMessage(role: 'user' | 'agent', content: string) {
      this.messages.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        role,
        content,
        timestamp: Date.now(),
      })
    },
    simulateAgentResponse() {
      // Clear any pending timeout to prevent stale callbacks
      if (this._simulateTimeoutId !== null) {
        clearTimeout(this._simulateTimeoutId)
      }

      this.loading = true
      this._simulateTimeoutId = setTimeout(() => {
        this._simulateTimeoutId = null

        const lastMsg = this.messages[this.messages.length - 1]?.content || ''
        let response = '这是 FDE AI 平台的模拟回复。接入真实后端 API 后将获得实际分析结果。'

        if (lastMsg.includes('搜索') || lastMsg.includes('search')) {
          response = '🔍 正在检索企业知识库...找到3份相关文档。报告已生成至右侧编辑器。'
        } else if (lastMsg.includes('地图') || lastMsg.includes('map')) {
          response = '🗺️ 地图数据已加载。请在地图上选择分析区域，或输入具体地点名称。'
        } else if (lastMsg.includes('员工') || lastMsg.includes('HR')) {
          response = '👥 HR 分析模块就绪。支持员工画像、风险评估和裁员模拟（含防呆确认）。'
        }

        this.addMessage('agent', response)
        this.loading = false
      }, 800)
    },
    /** Cancel any pending simulateAgentResponse timeout. */
    cancelSimulation() {
      if (this._simulateTimeoutId !== null) {
        clearTimeout(this._simulateTimeoutId)
        this._simulateTimeoutId = null
        this.loading = false
      }
    },
  },
})
