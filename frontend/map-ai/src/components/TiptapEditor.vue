<script setup lang="ts">
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Highlight from '@tiptap/extension-highlight'
import Link from '@tiptap/extension-link'
import { ref, onBeforeUnmount } from 'vue'

const isCollapsed = ref(false)

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

const editor = useEditor({
  content: '<p>FDE 地图AI分析报告</p><p>在地图上选择区域或输入查询，AI Agent 将自动生成分析报告。</p>',
  extensions: [
    StarterKit,
    Highlight,
    Link.configure({ openOnClick: false }),
  ],
  editorProps: {
    attributes: {
      class: 'editor-content',
    },
  },
})

// Destroy editor on component unmount to prevent memory leaks
onBeforeUnmount(() => {
  editor.value?.destroy()
})
</script>

<template>
  <section class="editor-section" :class="{ collapsed: isCollapsed }">
    <div class="editor-header" @click="toggleCollapse">
      <span>📝 分析笔记</span>
      <span class="editor-toolbar" @click.stop>
        <button v-if="editor && !isCollapsed" @click="editor.chain().focus().toggleBold().run()"
          class="toolbar-btn toolbar-btn--bold">
          B
        </button>
        <button v-if="editor && !isCollapsed" @click="editor.chain().focus().toggleHighlight().run()"
          class="toolbar-btn toolbar-btn--highlight">
          H
        </button>
        <button class="collapse-btn" :title="isCollapsed ? '展开' : '折叠'">
          {{ isCollapsed ? '◀' : '▶' }}
        </button>
      </span>
    </div>
    <EditorContent v-if="!isCollapsed" :editor="editor" />
  </section>
</template>
