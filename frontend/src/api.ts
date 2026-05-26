import type { Article, Asset, PublicSettings, PublishJob, SettingsStatus } from './types'

export type PublishPipelineResult = {
  cover_asset: Asset | null
  draft_job: PublishJob | null
  publish_job: PublishJob | null
  error: string | null
  stage: string
}

type Paginated<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(formatApiError(text, response.statusText))
  }
  return response.json() as Promise<T>
}

function formatApiError(text: string, fallback: string): string {
  if (!text) return fallback
  try {
    const payload = JSON.parse(text)
    if (typeof payload.detail === 'string') return payload.detail
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item: { msg?: string }) => item.msg || JSON.stringify(item))
        .join('\n')
    }
    return JSON.stringify(payload)
  } catch {
    return text
  }
}

export const api = {
  status: () => request<SettingsStatus>('/api/settings/status'),
  testAi: () => request<Record<string, unknown>>('/api/settings/ai/test'),
  appSettings: () => request<PublicSettings>('/api/settings/app'),
  saveAppSettings: (payload: PublicSettings) =>
    request<PublicSettings>('/api/settings/app', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  articles: async () => {
    const res = await request<Paginated<Article> | Article[]>('/api/articles')
    return Array.isArray(res) ? res : res.items
  },
  jobs: async () => {
    const res = await request<Paginated<PublishJob> | PublishJob[]>('/api/publish/jobs')
    return Array.isArray(res) ? res : res.items
  },
  deleteArticle: (articleId: number) =>
    request<{ ok: boolean }>(`/api/articles/${articleId}`, { method: 'DELETE' }),
  formatArticle: (articleId: number) =>
    request<Article>(`/api/articles/${articleId}/format`, { method: 'POST' }),
  createFromMarkdown: (markdown: string, instruction: string, title?: string) =>
    request<Article>('/api/articles/from-markdown', {
      method: 'POST',
      body: JSON.stringify({ markdown, instruction, title: title || null }),
    }),
  createFromTopic: (topic: string, audience: string, style: string, wordCount: number) =>
    request<Article>('/api/articles/from-topic', {
      method: 'POST',
      body: JSON.stringify({
        topic,
        audience: audience || null,
        style: style || null,
        word_count: wordCount,
      }),
    }),
  regenerate: (articleId: number, instruction: string) =>
    request<Article>(`/api/articles/${articleId}/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    }),
  createDraft: (articleId: number, thumbMediaId: string) =>
    request<PublishJob>(
      `/api/publish/articles/${articleId}?thumb_media_id=${encodeURIComponent(thumbMediaId)}`,
      {
        method: 'POST',
        body: JSON.stringify({ action: 'create_draft' }),
      },
    ),
  publish: (articleId: number, draftMediaId?: string) => {
    const suffix = draftMediaId ? `?draft_media_id=${encodeURIComponent(draftMediaId)}` : ''
    return request<PublishJob>(`/api/publish/articles/${articleId}${suffix}`, {
      method: 'POST',
      body: JSON.stringify({ action: 'publish' }),
    })
  },
  uploadCover: async (file: File, articleId?: number) => {
    const form = new FormData()
    form.append('file', file)
    const suffix = articleId ? `?article_id=${articleId}` : ''
    const response = await fetch(`/api/publish/cover${suffix}`, {
      method: 'POST',
      body: form,
    })
    if (!response.ok) {
      throw new Error(formatApiError(await response.text(), response.statusText))
    }
    return response.json() as Promise<Asset>
  },
  runAutoPublish: async (
    articleId: number,
    opts: { thumbMediaId?: string; coverFile?: File | null } = {},
  ) => {
    const url = `/api/publish/articles/${articleId}/pipeline`
    if (opts.coverFile) {
      const form = new FormData()
      form.append('file', opts.coverFile)
      if (opts.thumbMediaId) {
        form.append('payload', JSON.stringify({ thumb_media_id: opts.thumbMediaId }))
      }
      const response = await fetch(url, { method: 'POST', body: form })
      if (!response.ok) {
        throw new Error(formatApiError(await response.text(), response.statusText))
      }
      return response.json() as Promise<PublishPipelineResult>
    }
    return request<PublishPipelineResult>(url, {
      method: 'POST',
      body: JSON.stringify({ thumb_media_id: opts.thumbMediaId || null }),
    })
  },
  pollPublishJob: (jobId: number) =>
    request<PublishJob>(`/api/publish/jobs/${jobId}/poll`, { method: 'POST' }),
  pollAllPublishingJobs: () =>
    request<PublishJob[]>('/api/publish/jobs/poll-all', { method: 'POST' }),
}
