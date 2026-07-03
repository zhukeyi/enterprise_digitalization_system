<template>
  <div class="chat-input">
    <div v-if="capturedText" class="captured-hint">
      Captured: "{{ capturedText }}"
      <button class="hint-close" @click="capturedText = ''">x</button>
    </div>
    <div class="input-row">
      <textarea
        v-model="text"
        @keydown.enter.exact.prevent="send"
        @keydown.enter.shift.exact="text += '\n'"
        placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
        rows="2"
        :disabled="disabled"
        ref="textareaEl"
      ></textarea>
      <button @click="send" :disabled="disabled || !text.trim()" class="send-btn">
        Send
      </button>
    </div>
    <div class="capture-status">
      <span class="hint">Cmd+Shift+Space to capture & paste text</span>
    </div>
  </div>
</template>

<script>
import { ref, watch, onMounted } from "vue";

export default {
  name: "ChatInput",
  emits: ["send"],
  props: { disabled: { type: Boolean, default: false } },
  setup(props, { emit }) {
    const text = ref("");
    const capturedText = ref("");
    const textareaEl = ref(null);

    const send = () => {
      if (!text.value.trim()) return;
      emit("send", text.value);
      text.value = "";
    };

    // Listen for global paste (simulates text capture)
    const onPaste = (e) => {
      const paste = e.clipboardData?.getData("text/plain");
      if (paste) {
        capturedText.value = paste;
        text.value = paste;
      }
    };

    onMounted(() => {
      document.addEventListener("paste", onPaste);
    });

    watch(text, () => {
      if (capturedText.value && text.value !== capturedText.value) {
        capturedText.value = "";
      }
    });

    return { text, capturedText, send, textareaEl };
  },
};
</script>

<style scoped>
.chat-input {
  padding: 8px 12px 12px;
  border-top: 1px solid #333;
  background: #0f3460;
}
.captured-hint {
  font-size: 11px;
  color: #4fc3f7;
  margin-bottom: 4px;
  display: flex;
  justify-content: space-between;
}
.hint-close { background: none; border: none; color: #888; cursor: pointer; }
.input-row { display: flex; gap: 8px; align-items: flex-end; }
textarea {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #444;
  border-radius: 8px;
  background: #1a1a2e;
  color: #e0e0e0;
  font-size: 13px;
  resize: none;
  outline: none;
}
textarea:focus { border-color: #1a73e8; }
.send-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: #1a73e8;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.send-btn:disabled { opacity: 0.4; cursor: default; }
.capture-status { margin-top: 4px; }
.hint { font-size: 10px; color: #666; }
</style>