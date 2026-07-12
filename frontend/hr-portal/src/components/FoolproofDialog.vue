<script setup lang="ts">
import { ref, computed } from 'vue'

export interface FoolproofStep {
  key: string
  title: string
  description: string
  result: string
  warning: boolean
}

const props = defineProps<{
  visible: boolean
  departmentName: string
  analysisResult: Record<string, any> | null
}>()

const emit = defineEmits<{
  close: []
  confirm: []
}>()

const currentStep = ref(0)
const confirmed = ref(false)
const confirmText = ref('')

const steps: FoolproofStep[] = [
  {
    key: 'reversibility',
    title: '第 1 步：可逆性检查',
    description: '裁员决策是否可逆？一旦执行，重新招聘和培训的成本极高。',
    result: '此操作将永久影响涉及员工的工作关系。撤销裁员的平均成本为原薪资的 1.5-2 倍（重新招聘+培训+磨合期）。',
    warning: true,
  },
  {
    key: 'impact',
    title: '第 2 步：影响范围评估',
    description: '裁员将影响哪些人员和业务环节？',
    result: '影响范围包括被裁员工及其家属、留任员工的士气与工作量分配、部门整体产出能力以及企业雇主品牌。',
    warning: true,
  },
  {
    key: 'explanation',
    title: '第 3 步：通俗解释',
    description: '用非技术语言说明裁员方案的逻辑和依据。',
    result: '系统根据员工绩效、能力匹配度、岗位关键性和离职风险评估，识别出冗余岗位。这不是对个人能力的否定，而是组织结构优化的需要。',
    warning: false,
  },
  {
    key: 'confirm',
    title: '第 4 步：二次确认',
    description: '请输入"确认裁员"以继续。此操作不可撤销。',
    result: '',
    warning: true,
  },
  {
    key: 'snapshot',
    title: '第 5 步：方案快照',
    description: '系统将为此次操作生成快照存档，供审计追溯。',
    result: '快照将包含操作时间、操作者、涉及员工列表、裁员依据和风险评估结果。',
    warning: false,
  },
]

const currentStepData = computed(() => steps[currentStep.value])
const isLastStep = computed(() => currentStep.value === steps.length - 1)
const canProceed = computed(() => {
  if (currentStep.value === 3) return confirmText.value === '确认裁员'
  return true
})

function nextStep() {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++
  }
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

function handleClose() {
  currentStep.value = 0
  confirmText.value = ''
  confirmed.value = false
  emit('close')
}

function handleConfirm() {
  confirmed.value = true
  emit('confirm')
  currentStep.value = 0
  confirmText.value = ''
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="overlay" @click.self="handleClose">
      <div class="dialog">
        <div class="dialog-header">
          <h2>裁员方案确认 — 防呆 5 步</h2>
          <button class="close-btn" @click="handleClose">×</button>
        </div>

        <div class="dialog-body">
          <div class="dept-banner">
            目标部门：<strong>{{ departmentName }}</strong>
          </div>

          <div class="step-indicator">
            <div
              v-for="(s, i) in steps"
              :key="s.key"
              class="step-dot"
              :class="{ active: i === currentStep, done: i < currentStep }"
            >
              <span class="dot-num">{{ i < currentStep ? '✓' : i + 1 }}</span>
              <span class="dot-label">{{ s.title.split('：')[1] }}</span>
            </div>
          </div>

          <div class="step-content">
            <h3>{{ currentStepData.title }}</h3>
            <p class="step-desc">{{ currentStepData.description }}</p>

            <div v-if="currentStepData.result" class="step-result" :class="{ warning: currentStepData.warning }">
              {{ currentStepData.result }}
            </div>

            <div v-if="currentStep === 1 && analysisResult" class="impact-data">
              <div class="impact-item">
                <span class="impact-label">涉及人数</span>
                <span class="impact-value">{{ analysisResult.affected_count || analysisResult.headcount || '—' }}</span>
              </div>
              <div class="impact-item">
                <span class="impact-label">预计节省</span>
                <span class="impact-value">¥{{ ((analysisResult.estimated_savings || 0) / 10000).toFixed(1) }}万/年</span>
              </div>
              <div class="impact-item">
                <span class="impact-label">风险等级</span>
                <span class="impact-value" :class="analysisResult.risk_level">{{ analysisResult.risk_level || '—' }}</span>
              </div>
            </div>

            <div v-if="currentStep === 3" class="confirm-input-area">
              <input
                v-model="confirmText"
                class="confirm-input"
                placeholder='请输入"确认裁员"'
                type="text"
              />
              <p class="confirm-hint">输入"确认裁员"四个字后可继续</p>
            </div>

            <div v-if="currentStep === 4" class="snapshot-info">
              <div class="snapshot-card">
                <div class="snap-row"><span>操作时间</span><span>{{ new Date().toLocaleString('zh-CN') }}</span></div>
                <div class="snap-row"><span>部门</span><span>{{ departmentName }}</span></div>
                <div class="snap-row"><span>状态</span><span class="ready">就绪 — 点击下方按钮执行</span></div>
              </div>
            </div>
          </div>
        </div>

        <div class="dialog-footer">
          <button v-if="currentStep > 0" class="btn btn-secondary" @click="prevStep">上一步</button>
          <button v-if="!isLastStep" class="btn btn-primary" :disabled="!canProceed" @click="nextStep">下一步</button>
          <button v-if="isLastStep" class="btn btn-danger" @click="handleConfirm">执行裁员方案</button>
          <button class="btn btn-cancel" @click="handleClose">取消</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.dialog {
  background: #fff;
  border-radius: 14px;
  width: 640px;
  max-width: 92vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.dialog-header h2 {
  font-size: 17px;
  font-weight: 700;
  color: #1e40af;
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #9ca3af;
  cursor: pointer;
  line-height: 1;
}

.close-btn:hover {
  color: #1f2937;
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

.dept-banner {
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 14px;
  color: #92400e;
  margin-bottom: 18px;
}

.step-indicator {
  display: flex;
  justify-content: space-between;
  margin-bottom: 24px;
}

.step-dot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex: 1;
}

.dot-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
  border: 2px solid #d1d5db;
  color: #6b7280;
  background: #f9fafb;
}

.step-dot.active .dot-num {
  border-color: #2563eb;
  color: #2563eb;
  background: #dbeafe;
}

.step-dot.done .dot-num {
  border-color: #22c55e;
  color: #fff;
  background: #22c55e;
}

.dot-label {
  font-size: 11px;
  color: #6b7280;
  text-align: center;
}

.step-dot.active .dot-label {
  color: #2563eb;
  font-weight: 600;
}

.step-content h3 {
  font-size: 16px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 8px;
}

.step-desc {
  font-size: 14px;
  color: #6b7280;
  margin: 0 0 14px;
  line-height: 1.5;
}

.step-result {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
  padding: 14px;
  font-size: 14px;
  color: #075985;
  line-height: 1.6;
}

.step-result.warning {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}

.impact-data {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-top: 14px;
}

.impact-item {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  text-align: center;
}

.impact-label {
  display: block;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.impact-value {
  display: block;
  font-size: 18px;
  font-weight: 700;
  color: #1f2937;
}

.impact-value.high { color: #ef4444; }
.impact-value.medium { color: #f59e0b; }
.impact-value.low { color: #22c55e; }

.confirm-input-area {
  margin-top: 14px;
}

.confirm-input {
  width: 100%;
  padding: 12px 14px;
  border: 2px solid #d1d5db;
  border-radius: 8px;
  font-size: 15px;
  outline: none;
  transition: border-color 0.2s;
}

.confirm-input:focus {
  border-color: #2563eb;
}

.confirm-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
}

.snapshot-info {
  margin-top: 14px;
}

.snapshot-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px;
}

.snap-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 14px;
  border-bottom: 1px solid #f3f4f6;
}

.snap-row:last-child {
  border-bottom: none;
}

.snap-row span:first-child {
  color: #6b7280;
}

.snap-row span:last-child {
  font-weight: 600;
  color: #1f2937;
}

.snap-row .ready {
  color: #22c55e;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
}

.btn {
  padding: 9px 18px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-primary {
  background: #2563eb;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-secondary {
  background: #f3f4f6;
  color: #374151;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.btn-danger {
  background: #dc2626;
  color: #fff;
}

.btn-danger:hover {
  background: #b91c1c;
}

.btn-cancel {
  background: #fff;
  color: #6b7280;
  border: 1px solid #d1d5db;
}

.btn-cancel:hover {
  background: #f9fafb;
}
</style>
