export type Article = {
  id: number
  title: string
  source_type: string
  source_markdown?: string | null
  topic_prompt?: string | null
  current_html?: string | null
  digest?: string | null
  cover_prompt?: string | null
  tags: string[]
  status: string
  created_at: string
  updated_at: string
}

export type PublishJob = {
  id: number
  article_id: number
  target: string
  action: string
  status: string
  draft_media_id?: string | null
  publish_id?: string | null
  response_payload: Record<string, unknown>
  error?: string | null
  created_at: string
  updated_at: string
}

export type Asset = {
  id: number
  article_id?: number | null
  source_url: string
  local_path?: string | null
  wechat_url?: string | null
  media_id?: string | null
  asset_type: string
  status: string
  error?: string | null
  created_at: string
}

export type SettingsStatus = {
  openai_configured: boolean
  openai_model: string
  wechat: {
    ok: boolean
    checks: Record<string, boolean>
    message: string
  }
}
