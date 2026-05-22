<script setup lang="ts">
import {
  Bot,
  CheckCircle2,
  FileText,
  Loader2,
  RefreshCw,
  Send,
  Settings,
  Upload,
} from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { api } from './api'
import type { Article, PublishJob, SettingsStatus } from './types'

const articles = ref<Article[]>([])
const jobs = ref<PublishJob[]>([])
const status = ref<SettingsStatus | null>(null)
const selectedArticleId = ref<number | null>(null)
const markdown = ref('# 标题\n\n这里粘贴 Markdown 正文。')
const markdownInstruction = ref('请润色成适合公众号发布的文章，保留原文事实。')
const markdownTitle = ref('')
const topic = ref('')
const audience = ref('')
const style = ref('专业、清晰、有温度')
const wordCount = ref(1200)
const regenerateInstruction = ref('优化标题和段落节奏，让文章更适合公众号阅读。')
const thumbMediaId = ref('')
const draftMediaId = ref('')
const coverFile = ref<File | null>(null)
const activeTab = ref<'markdown' | 'topic'>('markdown')
const loading = ref(false)
const error = ref('')

const selectedArticle = computed(() =>
  articles.value.find((article) => article.id === selectedArticleId.value) ?? articles.value[0] ?? null,
)

async function refreshAll() {
  error.value = ''
  const [settingsResult, articleResult, jobResult] = await Promise.allSettled([
    api.status(),
    api.articles(),
    api.jobs(),
  ])
  if (settingsResult.status === 'fulfilled') {
    status.value = settingsResult.value
  }
  if (articleResult.status === 'fulfilled') {
    articles.value = articleResult.value
  }
  if (jobResult.status === 'fulfilled') {
    jobs.value = jobResult.value
  }
  const failures = [settingsResult, articleResult, jobResult].filter(
    (result) => result.status === 'rejected',
  )
  if (failures.length > 0) {
    error.value = failures
      .map((result) => (result.status === 'rejected' ? result.reason.message : ''))
      .filter(Boolean)
      .join('\n')
  }
  if (!selectedArticleId.value && articles.value.length > 0) {
    selectedArticleId.value = articles.value[0].id
  }
}

async function runTask(task: () => Promise<unknown>) {
  loading.value = true
  error.value = ''
  try {
    await task()
    await refreshAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function createMarkdownArticle() {
  await runTask(async () => {
    const created = await api.createFromMarkdown(
      markdown.value,
      markdownInstruction.value,
      markdownTitle.value,
    )
    selectedArticleId.value = created.id
  })
}

async function createTopicArticle() {
  await runTask(async () => {
    const created = await api.createFromTopic(topic.value, audience.value, style.value, wordCount.value)
    selectedArticleId.value = created.id
  })
}

async function regenerate() {
  if (!selectedArticle.value) return
  await runTask(async () => {
    const updated = await api.regenerate(selectedArticle.value!.id, regenerateInstruction.value)
    selectedArticleId.value = updated.id
  })
}

async function createDraft() {
  if (!selectedArticle.value) return
  await runTask(async () => {
    const job = await api.createDraft(selectedArticle.value!.id, thumbMediaId.value)
    if (job.draft_media_id) draftMediaId.value = job.draft_media_id
  })
}

async function uploadCover() {
  if (!coverFile.value) return
  await runTask(async () => {
    const asset = await api.uploadCover(coverFile.value!, selectedArticle.value?.id)
    if (asset.media_id) thumbMediaId.value = asset.media_id
  })
}

async function publishArticle() {
  if (!selectedArticle.value) return
  await runTask(async () => {
    await api.publish(selectedArticle.value!.id, draftMediaId.value || undefined)
  })
}

function statusClass(value: boolean) {
  return value ? 'ok' : 'warn'
}

onMounted(() => {
  runTask(refreshAll)
})
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>自动推文助手</h1>
        <p>Markdown 与主题生成到微信公众号草稿/发布工作台</p>
      </div>
      <button class="icon-button" :disabled="loading" title="刷新" @click="runTask(refreshAll)">
        <Loader2 v-if="loading" class="spin" :size="18" />
        <RefreshCw v-else :size="18" />
      </button>
    </header>

    <section class="status-strip" v-if="status">
      <div class="status-item">
        <Bot :size="18" />
        <span>OpenAI</span>
        <strong :class="statusClass(status.openai_configured)">
          {{ status.openai_configured ? status.openai_model : '未配置' }}
        </strong>
      </div>
      <div class="status-item">
        <Settings :size="18" />
        <span>微信接口</span>
        <strong :class="statusClass(status.wechat.ok)">
          {{ status.wechat.ok ? '可用' : '待配置' }}
        </strong>
      </div>
      <p>{{ status.wechat.message }}</p>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="workspace">
      <aside class="panel list-panel">
        <div class="panel-title">
          <FileText :size="18" />
          <span>文章</span>
        </div>
        <button
          v-for="article in articles"
          :key="article.id"
          class="article-row"
          :class="{ active: selectedArticle?.id === article.id }"
          @click="selectedArticleId = article.id"
        >
          <span>{{ article.title }}</span>
          <small>{{ article.status }} · {{ article.source_type }}</small>
        </button>
        <p v-if="articles.length === 0" class="empty">还没有文章。</p>
      </aside>

      <section class="panel editor-panel">
        <div class="tabs">
          <button :class="{ active: activeTab === 'markdown' }" @click="activeTab = 'markdown'">
            <Upload :size="16" />
            Markdown
          </button>
          <button :class="{ active: activeTab === 'topic' }" @click="activeTab = 'topic'">
            <Bot :size="16" />
            主题生成
          </button>
        </div>

        <div v-if="activeTab === 'markdown'" class="form-grid">
          <label>
            标题
            <input v-model="markdownTitle" placeholder="可留空，由 AI 生成" />
          </label>
          <label>
            AI 指令
            <input v-model="markdownInstruction" />
          </label>
          <label class="wide">
            Markdown
            <textarea v-model="markdown" rows="14" />
          </label>
          <button class="primary" :disabled="loading" @click="createMarkdownArticle">
            <Bot :size="18" />
            生成公众号文章
          </button>
        </div>

        <div v-else class="form-grid">
          <label>
            主题
            <input v-model="topic" placeholder="例如：AI 写作工具如何提升内容生产效率" />
          </label>
          <label>
            目标读者
            <input v-model="audience" placeholder="例如：独立开发者、运营人员" />
          </label>
          <label>
            风格
            <input v-model="style" />
          </label>
          <label>
            字数
            <input v-model.number="wordCount" type="number" min="300" max="5000" />
          </label>
          <button class="primary" :disabled="loading || !topic" @click="createTopicArticle">
            <Bot :size="18" />
            从主题生成文章
          </button>
        </div>
      </section>

      <section class="panel preview-panel">
        <div class="preview-head">
          <div>
            <h2>{{ selectedArticle?.title || '预览' }}</h2>
            <p>{{ selectedArticle?.digest || '选择或生成一篇文章后查看公众号预览。' }}</p>
          </div>
          <span v-if="selectedArticle" class="badge">{{ selectedArticle.status }}</span>
        </div>
        <div class="preview-body" v-html="selectedArticle?.current_html || ''" />
      </section>

      <section class="panel action-panel">
        <div class="panel-title">
          <Send :size="18" />
          <span>发布</span>
        </div>
        <label>
          封面 thumb_media_id
          <input v-model="thumbMediaId" placeholder="先在公众号素材接口上传封面，填入 media_id" />
        </label>
        <label>
          上传封面
          <input
            type="file"
            accept="image/*"
            @change="coverFile = ($event.target as HTMLInputElement).files?.[0] || null"
          />
        </label>
        <button :disabled="loading || !coverFile" @click="uploadCover">
          <Upload :size="18" />
          上传封面素材
        </button>
        <button class="primary" :disabled="loading || !selectedArticle || !thumbMediaId" @click="createDraft">
          <CheckCircle2 :size="18" />
          创建草稿
        </button>
        <label>
          草稿 media_id
          <input v-model="draftMediaId" placeholder="创建草稿后自动填入，也可手动填写" />
        </label>
        <button class="danger" :disabled="loading || !selectedArticle" @click="publishArticle">
          <Send :size="18" />
          自动发布
        </button>
        <label>
          再生成指令
          <input v-model="regenerateInstruction" />
        </label>
        <button :disabled="loading || !selectedArticle" @click="regenerate">
          <RefreshCw :size="18" />
          重新润色
        </button>

        <div class="jobs">
          <h3>任务日志</h3>
          <div v-for="job in jobs.slice(0, 8)" :key="job.id" class="job-row">
            <span>{{ job.action }}</span>
            <strong :class="job.status">{{ job.status }}</strong>
            <small>{{ job.error || job.draft_media_id || job.publish_id }}</small>
          </div>
          <p v-if="jobs.length === 0" class="empty">暂无发布任务。</p>
        </div>
      </section>
    </div>
  </main>
</template>
