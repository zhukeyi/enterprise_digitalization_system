<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { askData, type AskResult, type AskSource } from '../api/client'

const query = ref('')
const loading = ref(false)
const error = ref('')
const messages = ref<{ role: 'user' | 'ai'; text: string; sources?: AskSource[] }[]>([])
const box = ref<HTMLElement | null>(null)

async function send() {
  const q = query.value.trim()
  if (!q || loading.value) return
  messages.value.push({ role: 'user', text: q })
  query.value = ''
  loading.value = true
  error.value = ''
  try {
    const res: AskResult = await askData(q)
    messages.value.push({ role: 'ai', text: res.answer, sources: res.sources })
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
      ?.response?.data?.detail
    error.value = detail || (err as { message?: string })?.message || '请求失败'
    messages.value.push({ role: 'ai', text: `⚠️ ${error.value}` })
  } finally {
    loading.value = false
    await nextTick()
    box.value?.scrollTo({ top: box.value.scrollHeight })
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <section class="chat">
    <h2>数据问答</h2>
    <p class="hint">基于已上传的数据提问，命中结果会展示答案与来源。</p>

    <div ref="box" class="messages">
      <div v-if="messages.length === 0" class="empty">还没有对话，先去「上传」一份 Excel 再回来提问吧。</div>
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="msg"
        :class="m.role"
      >
        <div class="bubble">{{ m.text }}</div>
        <div v-if="m.sources && m.sources.length" class="sources">
          <div class="src-title">来源（{{ m.sources.length }}）</div>
          <div v-for="(s, j) in m.sources" :key="j" class="src">
            <span class="src-doc">{{ s.doc_type }}</span>
            <span class="src-text">{{ s.text }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="composer">
      <textarea
        v-model="query"
        rows="2"
        placeholder="输入问题后回车发送…"
        @keydown="onKey"
      ></textarea>
      <button :disabled="loading" @click="send">{{ loading ? '思考中…' : '发送' }}</button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
  </section>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px - 48px);
}
h2 {
  margin: 0 0 4px;
  font-size: 18px;
  color: #1e3a8a;
}
.hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: #6b7280;
}
.messages {
  flex: 1;
  overflow-y: auto;
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.empty {
  color: #9ca3af;
  font-size: 14px;
  text-align: center;
  margin-top: 40px;
}
.msg {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
}
.msg.user {
  align-items: flex-end;
}
.bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user .bubble {
  background: #1e3a8a;
  color: #fff;
}
.msg.ai .bubble {
  background: #f1f5f9;
  color: #1f2937;
}
.sources {
  margin-top: 8px;
  max-width: 90%;
}
.src-title {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}
.src {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
  font-size: 12px;
}
.src-doc {
  display: inline-block;
  background: #dbeafe;
  color: #1e40af;
  border-radius: 4px;
  padding: 1px 6px;
  margin-right: 6px;
  font-size: 11px;
}
.src-text {
  color: #374151;
}
.composer {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
textarea {
  flex: 1;
  resize: none;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
}
textarea:focus {
  border-color: #3b82f6;
}
.composer button {
  height: 44px;
  padding: 0 22px;
  background: #1e3a8a;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  cursor: pointer;
}
.composer button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.err {
  color: #dc2626;
  font-size: 13px;
  margin: 8px 0 0;
}
</style>
