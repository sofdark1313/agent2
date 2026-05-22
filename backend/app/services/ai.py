import json

from openai import OpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.schemas import AiArticleResult
from app.services.content import apply_wechat_style, markdown_to_html, sanitize_html

ARTICLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "digest", "html", "cover_prompt", "tags"],
    "properties": {
        "title": {"type": "string"},
        "digest": {"type": ["string", "null"]},
        "html": {"type": "string"},
        "cover_prompt": {"type": ["string", "null"]},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


class AiService:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            self.client: OpenAI | None = None
        else:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def is_configured(self) -> bool:
        return self.client is not None

    def polish_markdown(self, markdown: str, instruction: str | None = None) -> AiArticleResult:
        fallback_html = apply_wechat_style(markdown_to_html(markdown))
        if not self.client:
            return AiArticleResult(
                title="未配置 OpenAI 的 Markdown 预览",
                digest="当前仅完成本地 Markdown 转换，配置 OPENAI_API_KEY 后可启用 AI 润色。",
                html=fallback_html,
                cover_prompt=None,
                tags=[],
            )

        prompt = f"""
你是一个微信公众号编辑。请在不虚构事实的前提下润色下面的 Markdown，输出适合公众号发布的 HTML。

要求：
- 保留原文事实、论点和关键细节。
- 优化标题、摘要、结构、段落节奏。
- HTML 只使用常见正文标签，不要输出 script、style 或外链追踪代码。
- 图片保留为原始 img src，后续系统会上传替换。

用户补充要求：{instruction or "无"}

Markdown:
{markdown}
"""
        return self._create_article(prompt)

    def generate_from_topic(
        self, topic: str, audience: str | None, style: str | None, word_count: int | None
    ) -> AiArticleResult:
        if not self.client:
            html = apply_wechat_style(
                markdown_to_html(
                    f"# {topic}\n\n请配置 OPENAI_API_KEY 后，让系统根据该主题生成完整公众号文章。"
                )
            )
            return AiArticleResult(
                title=topic,
                digest="OpenAI 未配置，已创建占位草稿。",
                html=html,
                cover_prompt=None,
                tags=[],
            )

        prompt = f"""
你是一个微信公众号作者。请根据主题直接生成一篇完整文章，并输出适合公众号发布的 HTML。

主题：{topic}
目标读者：{audience or "未指定"}
风格：{style or "清晰、专业、自然"}
目标字数：{word_count or 1200}

要求：
- 给出有吸引力但不夸张的标题。
- 摘要控制在 120 字以内。
- 内容结构完整，有小标题和自然结尾。
- 不编造具体数据、来源或案例；不确定的信息用审慎表达。
- HTML 只使用常见正文标签，不要输出 script、style 或外链追踪代码。
"""
        return self._create_article(prompt)

    def _create_article(self, prompt: str) -> AiArticleResult:
        assert self.client is not None
        response = self.client.responses.create(
            model=settings.openai_model,
            instructions="输出必须是满足 JSON Schema 的对象，html 字段必须是正文 HTML 字符串。",
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "wechat_article",
                    "strict": True,
                    "schema": ARTICLE_SCHEMA,
                }
            },
        )
        raw = response.output_text
        try:
            payload = json.loads(raw)
            payload["html"] = apply_wechat_style(sanitize_html(payload["html"]))
            return AiArticleResult.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(f"AI 返回内容无法解析: {exc}") from exc
