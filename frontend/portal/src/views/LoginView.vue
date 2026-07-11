<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const error = ref('')

function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value.trim()) {
    error.value = '请输入用户名和密码'
    return
  }
  auth.login()
  const redirect = (route.query.redirect as string) || '/upload'
  router.push(redirect)
}
</script>

<template>
  <div class="login-wrap">
    <div class="card">
      <h1>FDE 数据门户</h1>
      <p class="sub">登录以使用数据上传与问答</p>
      <label>用户名</label>
      <input v-model="username" placeholder="请输入用户名" />
      <label>密码</label>
      <input
        v-model="password"
        type="password"
        placeholder="请输入密码"
        @keyup.enter="submit"
      />
      <p v-if="error" class="err">{{ error }}</p>
      <button @click="submit">进入门户</button>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
}
.card {
  width: 320px;
  background: #fff;
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
h1 {
  margin: 0;
  font-size: 20px;
  color: #1e3a8a;
}
.sub {
  margin: 0 0 12px;
  font-size: 13px;
  color: #6b7280;
}
label {
  font-size: 13px;
  color: #374151;
  margin-top: 8px;
}
input {
  height: 38px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0 12px;
  font-size: 14px;
  outline: none;
}
input:focus {
  border-color: #3b82f6;
}
.err {
  color: #dc2626;
  font-size: 13px;
  margin: 4px 0 0;
}
button {
  margin-top: 16px;
  height: 40px;
  background: #1e3a8a;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  cursor: pointer;
}
button:hover {
  background: #1e40af;
}
</style>
