<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '../stores/chat'

const chatStore = useChatStore()
const inputText = ref('')

function sendMessage() {
  if (!inputText.value.trim()) return
  chatStore.addMessage('user', inputText.value)
  inputText.value = ''
  // Simulate agent response
  chatStore.simulateAgentResponse()
}
</script>

<template>
  <section class="chat-section">
    <div class="chat-header">
      🤖 FDE AI Agent
    </div>
    <div class="chat-messages">
      <div v-for="msg in chatStore.messages" :key="msg.id"
           :class="['message', msg.role]">
        <div class="bubble">{{ msg.content }}</div>
      </div>
      <div v-if="chatStore.loading" class="message agent">
        <div class="bubble" style="color: var(--fde-text-light)">
          ⏳ 正在思考...
        </div>
      </div>
    </div>
    <div class="chat-input-area">
      <textarea v-model="inputText" rows="2"
        placeholder="输入查询或指令..."
        @keydown.enter.prevent="sendMessage" />
      <button @click="sendMessage">发送</button>
    </div>
  </section>
</template>
