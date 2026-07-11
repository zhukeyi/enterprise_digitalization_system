<script setup lang="ts">
import { ref } from 'vue'
import { uploadExcel, type UploadResult } from '../api/client'

const file = ref<File | null>(null)
const docType = ref('excel_upload')
const loading = ref(false)
const message = ref('')
const error = ref('')
const result = ref<UploadResult | null>(null)

function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
  error.value = ''
  result.value = null
  message.value = ''
}

async function upload() {
  if (!file.value) {
    error.value = '请先选择 Excel 文件'
    return
  }
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const data = await uploadExcel(file.value, docType.value)
    result.value = data
    message.value = `入库成功：共 ${data.rows ?? '?'} 行，索引 ${data.indexed_vectors ?? '?'} 条向量`
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
      ?.response?.data?.detail
    error.value = detail || (err as { message?: string })?.message || '上传失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="panel">
    <h2>文件上传</h2>
    <p class="hint">上传一份 Excel（.xlsx / .xlsm）。乱列名会自动归一化后落库并进入向量检索。</p>

    <div class="form-row">
      <label>数据类型（doc_type）</label>
      <input v-model="docType" placeholder="excel_upload" />
    </div>

    <div class="form-row">
      <label>选择文件</label>
      <input type="file" accept=".xlsx,.xlsm" @change="onFile" />
    </div>

    <button :disabled="loading" @click="upload">
      {{ loading ? '入库中…' : '上传并入库' }}
    </button>

    <p v-if="message" class="ok">{{ message }}</p>
    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="result" class="result">
      <h3>入库结果</h3>
      <ul>
        <li><span>doc_type</span><code>{{ result.doc_type }}</code></li>
        <li><span>source_ref</span><code>{{ result.source_ref }}</code></li>
        <li><span>rows</span><code>{{ result.rows }}</code></li>
        <li><span>canonical</span><code>{{ result.canonical }}</code></li>
        <li><span>indexed_vectors</span><code>{{ result.indexed_vectors }}</code></li>
        <li><span>raw_id</span><code>{{ result.raw_id }}</code></li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
h2 {
  margin: 0 0 4px;
  font-size: 18px;
  color: #1e3a8a;
}
.hint {
  margin: 0 0 20px;
  font-size: 13px;
  color: #6b7280;
}
.form-row {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-row label {
  font-size: 13px;
  color: #374151;
}
.form-row input[type='text'],
.form-row input:not([type]) {
  height: 38px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 0 12px;
  font-size: 14px;
}
button {
  height: 40px;
  padding: 0 20px;
  background: #1e3a8a;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.ok {
  color: #16a34a;
  font-size: 14px;
  margin-top: 16px;
}
.err {
  color: #dc2626;
  font-size: 14px;
  margin-top: 16px;
}
.result {
  margin-top: 20px;
  border-top: 1px solid #e5e7eb;
  padding-top: 16px;
}
.result h3 {
  font-size: 14px;
  color: #374151;
  margin: 0 0 12px;
}
.result ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.result li {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px dashed #f0f0f0;
  font-size: 13px;
}
.result span {
  color: #6b7280;
}
.result code {
  color: #1e3a8a;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
