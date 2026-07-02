<script setup lang="ts">
/**
 * VoiceTextInput — Voice + text hybrid input (M3-T9).
 *
 * Uses the Web Speech API (SpeechRecognition) for voice input with
 * graceful degradation to text-only mode when the API is unavailable.
 * Features:
 * - Toggle voice recording with mic button
 * - Real-time transcription display (interim results)
 * - Text input fallback always available
 * - Visual recording indicator (pulsing red dot)
 */
import { ref, onBeforeUnmount } from 'vue'

const props = defineProps<{
  placeholder?: string
}>()

const emit = defineEmits<{
  submit: [text: string]
}>()

const text = ref('')
const isRecording = ref(false)
const interimText = ref('')
const speechSupported = ref(false)
const errorMessage = ref('')

// SpeechRecognition instance (browser API, not in standard TS types)
let recognition: any = null

function initSpeechRecognition() {
  const SpeechRecognitionClass =
    (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognitionClass) {
    speechSupported.value = false
    return
  }
  speechSupported.value = true
  recognition = new SpeechRecognitionClass()
  recognition.continuous = false
  recognition.interimResults = true
  recognition.lang = 'zh-CN'

  recognition.onresult = (event: any) => {
    let interim = ''
    let final = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript
      if (event.results[i].isFinal) {
        final += transcript
      } else {
        interim += transcript
      }
    }
    interimText.value = interim
    if (final) {
      text.value += final
      interimText.value = ''
    }
  }

  recognition.onerror = (event: any) => {
    if (event.error === 'not-allowed') {
      errorMessage.value = '麦克风权限被拒绝'
    } else if (event.error === 'no-speech') {
      errorMessage.value = '未检测到语音'
    } else {
      errorMessage.value = `语音识别错误: ${event.error}`
    }
    isRecording.value = false
    // Clear error after 3 seconds
    setTimeout(() => {
      errorMessage.value = ''
    }, 3000)
  }

  recognition.onend = () => {
    isRecording.value = false
    interimText.value = ''
  }
}

function toggleRecording() {
  if (!speechSupported.value) {
    errorMessage.value = '浏览器不支持语音识别，请使用文本输入'
    setTimeout(() => {
      errorMessage.value = ''
    }, 3000)
    return
  }

  if (isRecording.value) {
    recognition?.stop()
    isRecording.value = false
  } else {
    try {
      recognition?.start()
      isRecording.value = true
      errorMessage.value = ''
    } catch {
      // Recognition already started — ignore
      isRecording.value = false
    }
  }
}

function submitText() {
  const value = text.value.trim()
  if (!value) return
  emit('submit', value)
  text.value = ''
  interimText.value = ''
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submitText()
  }
}

// Initialize on creation
initSpeechRecognition()

onBeforeUnmount(() => {
  if (isRecording.value) {
    recognition?.stop()
  }
})
</script>

<template>
  <div class="voice-text-input">
    <div class="input-row">
      <button
        class="mic-btn"
        :class="{ recording: isRecording, unsupported: !speechSupported }"
        :title="speechSupported ? '语音输入' : '浏览器不支持语音识别'"
        @click="toggleRecording"
      >
        <span v-if="isRecording" class="recording-dot" />
        <span v-else>🎙</span>
      </button>
      <div class="text-input-wrapper">
        <input
          v-model="text"
          type="text"
          :placeholder="placeholder || '输入分析指令...'"
          class="text-input"
          @keydown="handleKeydown"
        />
        <span v-if="interimText" class="interim-text">{{ interimText }}</span>
      </div>
      <button
        class="send-btn"
        :disabled="!text.trim()"
        @click="submitText"
      >
        发送
      </button>
    </div>
    <div v-if="errorMessage" class="error-msg">
      ⚠ {{ errorMessage }}
    </div>
    <div v-if="isRecording" class="recording-hint">
      正在录音... 点击麦克风停止
    </div>
  </div>
</template>

<style scoped>
.voice-text-input {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mic-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid #e0e4e8;
  border-radius: 8px;
  background: #f5f7fa;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.mic-btn:hover:not(.unsupported) {
  background: #e8f0fe;
  border-color: #1a73e8;
}

.mic-btn.recording {
  background: #ffebee;
  border-color: #c62828;
}

.mic-btn.unsupported {
  opacity: 0.4;
  cursor: not-allowed;
}

.recording-dot {
  width: 10px;
  height: 10px;
  background: #c62828;
  border-radius: 50%;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}

.text-input-wrapper {
  flex: 1;
  position: relative;
}

.text-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #e0e4e8;
  border-radius: 8px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}

.text-input:focus {
  border-color: #1a73e8;
}

.interim-text {
  position: absolute;
  top: 50%;
  left: 10px;
  transform: translateY(-50%);
  color: #999;
  font-size: 13px;
  pointer-events: none;
  font-style: italic;
}

.send-btn {
  padding: 8px 14px;
  border: none;
  border-radius: 8px;
  background: #1a73e8;
  color: white;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background: #1557b0;
}

.send-btn:disabled {
  background: #e0e0e0;
  color: #999;
  cursor: not-allowed;
}

.error-msg {
  font-size: 12px;
  color: #c62828;
  padding: 2px 4px;
}

.recording-hint {
  font-size: 12px;
  color: #c62828;
  padding: 2px 4px;
}
</style>
