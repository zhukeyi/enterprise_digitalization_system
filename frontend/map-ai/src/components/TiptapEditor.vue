<script setup lang="ts">
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Highlight from '@tiptap/extension-highlight'
import Link from '@tiptap/extension-link'

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
</script>

<template>
  <section class="editor-section">
    <div class="editor-header">
      📝 分析笔记
      <span style="float: right">
        <button v-if="editor" @click="editor.chain().focus().toggleBold().run()"
          style="background: var(--fde-bg); border: 1px solid var(--fde-border); padding: 2px 6px; margin-left: 4px; border-radius: 4px; cursor: pointer; font-size: 11px;">
          B
        </button>
        <button v-if="editor" @click="editor.chain().focus().toggleHighlight().run()"
          style="background: var(--fde-accent-light); border: 1px solid var(--fde-accent); padding: 2px 6px; margin-left: 4px; border-radius: 4px; cursor: pointer; font-size: 11px;">
          H
        </button>
      </span>
    </div>
    <EditorContent :editor="editor" />
  </section>
</template>
