import type { Article, Asset, PublishJob, SettingsStatus } from './types'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || response.statusText)
  }
  return response.json() as Promise<T>
}

export const api = {
  status: () => request<SettingsStatus>('/api/settings/status'),
  articles: () => request<Article[]>('/api/articles'),
  jobs: () => request<PublishJob[]>('/api/publish/jobs'),
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
      throw new Error((await response.text()) || response.statusText)
    }
    return response.json() as Promise<Asset>
  },
}
