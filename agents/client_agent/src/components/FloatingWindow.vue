<template>
  <div class="floating-window" :class="{ 'is-hidden': !visible }">
    <div class="titlebar" @dblclick="minimize">
      <span class="title">FDE AI Assistant</span>
      <button class="btn-icon" @click="minimize" title="Minimize">_</button>
    </div>

    <div class="content">
      <!-- Login form -->
      <LoginForm v-if="!authenticated" @authenticated="onAuthenticated" />

      <!-- Chat interface -->
      <div v-else class="chat-container">
        <div class="messages" ref="messagesEl">
          <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
            <div class="msg-role">{{ msg.role === 'user' ? 'You' : 'FDE AI' }}</div>
            <div class="msg-content">{{ msg.content }}</div>
          </div>
          <div v-if="loading" class="message assistant">
            <div class="msg-role">FDE AI</div>
            <div class="msg-content typing">...</div>
          </div>
        </div>

        <ChatInput @send="onSend" @text-capture="onTextCapture" :disabled="loading" />
      </div>
    </div>

    <!-- Settings panel -->
    <div v-if="showSettings" class="settings-panel">
      <h3>Settings</h3>
      <label>Server URL</label>
      <input v-model="serverUrl" placeholder="https://217.142.246.70:8443/api" />
      <label>JWT Token</label>
      <input v-model="jwtToken" type="password" />
      <div class="settings-actions">
        <button @click="saveSettings">Save</button>
        <button @click="showSettings = false">Close</button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, nextTick, onMounted } from "vue";
import LoginForm from "./LoginForm.vue";
import ChatInput from "./ChatInput.vue";

export default {
  name: "FloatingWindow",
  components: { LoginForm, ChatInput },
  setup() {
    const visible = ref(false);
    const authenticated = ref(false);
    const loading = ref(false);
    const showSettings = ref(false);
    const serverUrl = ref(localStorage.getItem("fde_server_url") || "https://217.142.246.70:8443/api");
    const jwtToken = ref(localStorage.getItem("fde_jwt_token") || "");
    const messages = ref([]);
    const messagesEl = ref(null);

    const minimize = () => {
      visible.value = !visible.value;
    };

    const onAuthenticated = (token) => {
      jwtToken.value = token;
      localStorage.setItem("fde_jwt_token", token);
      authenticated.value = true;
    };

    const saveSettings = () => {
      localStorage.setItem("fde_server_url", serverUrl.value);
      showSettings.value = false;
    };

    const scrollToBottom = () => {
      nextTick(() => {
        if (messagesEl.value) {
          messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
        }
      });
    };

    const onSend = async (text) => {
      if (!text.trim()) return;

      messages.value.push({ role: "user", content: text });
      scrollToBottom();

      loading.value = true;
      try {
        const response = await fetch(`${serverUrl.value}/v1/chat/completions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${jwtToken.value}`,
          },
          body: JSON.stringify({
            model: "fde-supervisor",
            messages: [{ role: "user", content: text }],
            stream: true,
          }),
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullContent = "";

        messages.value.push({ role: "assistant", content: "" });
        const lastIdx = messages.value.length - 1;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n").filter((l) => l.startsWith("data: "));
          for (const line of lines) {
            try {
              const data = JSON.parse(line.slice(6));
              const delta = data.choices?.[0]?.delta?.content || "";
              fullContent += delta;
              messages.value[lastIdx].content = fullContent;
            } catch {
              // skip malformed lines
            }
          }
        }
      } catch (e) {
        messages.value.push({ role: "assistant", content: `Error: ${e.message}` });
      } finally {
        loading.value = false;
        scrollToBottom();
      }
    };

    const onTextCapture = (capturedText) => {
      // Auto-fill captured text into input
      // Called by ChatInput when text is captured via global shortcut
    };

    onMounted(() => {
      // Check if already authenticated
      if (jwtToken.value) {
        authenticated.value = true;
      }
      // Show window on mount
      visible.value = true;
    });

    return {
      visible, authenticated, loading, showSettings,
      serverUrl, jwtToken, messages, messagesEl,
      minimize, onAuthenticated, saveSettings, onSend, onTextCapture,
    };
  },
};
</script>

<style scoped>
.floating-window {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #16213e;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}
.floating-window.is-hidden {
  display: none;
}
.titlebar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #0f3460;
  -webkit-app-region: drag;
  user-select: none;
}
.title {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
}
.btn-icon {
  -webkit-app-region: no-drag;
  background: none;
  border: none;
  color: #e0e0e0;
  font-size: 16px;
  cursor: pointer;
  padding: 0 8px;
}
.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.chat-container { display: flex; flex-direction: column; height: 100%; }
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.message { max-width: 85%; }
.message.user { align-self: flex-end; }
.message.assistant { align-self: flex-start; }
.msg-role { font-size: 11px; color: #888; margin-bottom: 2px; }
.msg-content {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.message.user .msg-content { background: #1a73e8; color: #fff; }
.message.assistant .msg-content { background: #2a2a4a; color: #e0e0e0; }
.typing { animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0.3; } }
.settings-panel {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: #16213e;
  padding: 24px;
  z-index: 10;
}
.settings-panel h3 { margin-bottom: 16px; }
.settings-panel label { display: block; font-size: 12px; margin: 8px 0 4px; color: #aaa; }
.settings-panel input {
  width: 100%;
  padding: 8px;
  border: 1px solid #444;
  border-radius: 4px;
  background: #1a1a2e;
  color: #e0e0e0;
  font-size: 13px;
}
.settings-actions { margin-top: 16px; display: flex; gap: 8px; }
.settings-actions button {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  background: #1a73e8;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}
</style>