import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// MVS 阶段：登录仅为 localStorage 标志位（后端 FDE_ENABLE_AUTH 关闭）。
// H3 阶段将替换为真实 JWT + 后端鉴权（见 master-delivery-plan.md）。
const STORAGE_KEY = 'fde_portal_auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(STORAGE_KEY))
  const isLoggedIn = computed(() => token.value === '1')

  function login() {
    token.value = '1'
    localStorage.setItem(STORAGE_KEY, '1')
  }
  function logout() {
    token.value = null
    localStorage.removeItem(STORAGE_KEY)
  }
  return { token, isLoggedIn, login, logout }
})
