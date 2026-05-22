<script setup lang="ts">
import {
  Bot,
  CheckCircle2,
  FileText,
  Loader2,
  Trash2,
  RefreshCw,
  Send,
  Settings,
  Upload,
} from 'lucide-vue-next'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from './api'
import type { Article, PublicSettings, PublishJob, SettingsStatus } from './types'

const articles = ref<Article[]>([])
const jobs = ref<PublishJob[]>([])
const status = ref<SettingsStatus | null>(null)
const appSettings = ref<PublicSettings>({
  default_author: '',
  wechat_account_name: '',
  wechat_original_id: '',
})
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
const aiTestMessage = ref('')
const taskMessage = ref('')
let pollTimer: number | undefined

const selectedArticle = computed(() =>
  articles.value.find((article) => article.id === selectedArticleId.value) ?? articles.value[0] ?? null,
)
const hasGeneratingArticle = computed(() =>
  articles.value.some((article) => article.status === 'generating'),
)

async function refreshAll() {
  error.value = ''
  const [settingsResult, appSettingsResult, articleResult, jobResult] = await Promise.allSettled([
    api.status(),
    api.appSettings(),
    api.articles(),
    api.jobs(),
  ])
  if (settingsResult.status === 'fulfilled') {
    status.value = settingsResult.value
  }
  if (appSettingsResult.status === 'fulfilled') {
    appSettings.value = appSettingsResult.value
  }
  if (articleResult.status === 'fulfilled') {
    articles.value = articleResult.value
  }
  if (jobResult.status === 'fulfilled') {
    jobs.value = jobResult.value
  }
  const failures = [settingsResult, appSettingsResult, articleResult, jobResult].filter(
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
    taskMessage.value = 'Markdown 已转换完成，可直接创建草稿。需要 AI 润色时，请点击右侧重新润色。'
  })
}

async function createTopicArticle() {
  await runTask(async () => {
    const created = await api.createFromTopic(topic.value, audience.value, style.value, wordCount.value)
    selectedArticleId.value = created.id
    taskMessage.value = '已提交生成任务，AI 正在后台处理。'
  })
}

async function regenerate() {
  if (!selectedArticle.value) return
  await runTask(async () => {
    const updated = await api.regenerate(selectedArticle.value!.id, regenerateInstruction.value)
    selectedArticleId.value = updated.id
    taskMessage.value = '已提交重新润色任务，AI 正在后台处理。'
  })
}

async function createDraft() {
  if (!selectedArticle.value) return
  await runTask(async () => {
    const job = await api.createDraft(selectedArticle.value!.id, thumbMediaId.value)
    if (job.status === 'failed') {
      throw new Error(job.error || '创建草稿失败')
    }
    if (job.draft_media_id) draftMediaId.value = job.draft_media_id
    taskMessage.value = '草稿创建成功。'
  })
}

async function uploadCover() {
  if (!coverFile.value) return
  await runTask(async () => {
    const asset = await api.uploadCover(coverFile.value!, selectedArticle.value?.id)
    if (asset.media_id) thumbMediaId.value = asset.media_id
    taskMessage.value = '封面素材上传成功。'
  })
}

async function publishArticle() {
  if (!selectedArticle.value) return
  await runTask(async () => {
    const job = await api.publish(selectedArticle.value!.id, draftMediaId.value || undefined)
    if (job.status === 'failed') {
      throw new Error(job.error || '自动发布失败')
    }
    taskMessage.value = '发布任务提交成功。'
  })
}

async function testAi() {
  await runTask(async () => {
    const result = await api.testAi()
    aiTestMessage.value = result.ok ? `AI 连通成功：${result.model}` : 'AI 连通失败'
  })
}

async function saveSettings() {
  await runTask(async () => {
    appSettings.value = await api.saveAppSettings(appSettings.value)
    taskMessage.value = '设置已保存。'
  })
}

async function deleteArticle(articleId: number) {
  if (!window.confirm('确定删除这篇文章？关联的发布任务和素材记录也会删除。')) return
  await runTask(async () => {
    await api.deleteArticle(articleId)
    if (selectedArticleId.value === articleId) {
      selectedArticleId.value = null
    }
    taskMessage.value = '文章已删除。'
  })
}

async function formatSelectedArticle() {
  if (!selectedArticle.value) return
  await runTask(async () => {
    const formatted = await api.formatArticle(selectedArticle.value!.id)
    selectedArticleId.value = formatted.id
    taskMessage.value = '文章已重新排版。'
  })
}

function statusClass(value: boolean) {
  return value ? 'ok' : 'warn'
}

onMounted(() => {
  runTask(refreshAll)
  pollTimer = window.setInterval(() => {
    if (hasGeneratingArticle.value) {
      refreshAll()
    }
  }, 3000)
})

onUnmounted(() => {
  if (pollTimer) {
    window.clearInterval(pollTimer)
  }
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
        <span>AI 模型</span>
        <strong :class="statusClass(status.ai_configured)">
          {{ status.ai_configured ? status.ai_model_name : '未配置' }}
        </strong>
      </div>
      <button :disabled="loading || !status.ai_configured" @click="testAi">
        <Bot :size="16" />
        测试 AI
      </button>
      <div class="status-item">
        <Settings :size="18" />
        <span>微信接口</span>
        <strong :class="statusClass(status.wechat.ok)">
          {{ status.wechat.ok ? '可用' : '待配置' }}
        </strong>
      </div>
      <p>{{ status.wechat.message }}</p>
      <p v-if="aiTestMessage">{{ aiTestMessage }}</p>
    </section>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="taskMessage || hasGeneratingArticle" class="notice">
      {{ hasGeneratingArticle ? 'AI 正在后台生成，页面会自动刷新。' : taskMessage }}
    </p>

    <div class="workspace">
      <aside class="panel list-panel">
        <div class="panel-title">
          <FileText :size="18" />
          <span>文章</span>
        </div>
        <div
          v-for="article in articles"
          :key="article.id"
          class="article-row"
          :class="{ active: selectedArticle?.id === article.id }"
        >
          <button class="article-select" @click="selectedArticleId = article.id">
            <span>{{ article.title }}</span>
            <small>{{ article.status }} · {{ article.source_type }}</small>
          </button>
          <button class="icon-button small" title="删除文章" @click="deleteArticle(article.id)">
            <Trash2 :size="15" />
          </button>
        </div>
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
            <input v-model="markdownTitle" placeholder="可留空，默认读取 Markdown 一级标题" />
          </label>
          <label>
            可选润色指令
            <input v-model="markdownInstruction" />
          </label>
          <label class="wide">
            Markdown
            <textarea v-model="markdown" rows="14" />
          </label>
          <button class="primary" :disabled="loading" @click="createMarkdownArticle">
            <Upload :size="18" />
            转换为公众号文章
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
            <input v-model.number="wordCount" type="number" min="100" max="5000" />
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
          <Settings :size="18" />
          <span>账号设置</span>
        </div>
        <label>
          默认作者
          <input v-model="appSettings.default_author" placeholder="创建微信草稿时写入 author 字段" />
        </label>
        <label>
          公众号名称
          <input v-model="appSettings.wechat_account_name" placeholder="用于本地标记关联账号" />
        </label>
        <label>
          原始 ID
          <input v-model="appSettings.wechat_original_id" placeholder="例如 gh_xxxxx，可选" />
        </label>
        <button :disabled="loading" @click="saveSettings">
          <Settings :size="18" />
          保存设置
        </button>

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
        <button class="primary" :disabled="loading || !selectedArticle" @click="createDraft">
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
        <button :disabled="loading || !selectedArticle" @click="formatSelectedArticle">
          <RefreshCw :size="18" />
          重新排版
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
