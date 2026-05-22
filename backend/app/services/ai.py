import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.schemas import AiArticleResult
from app.services.content import apply_wechat_style, markdown_to_html, sanitize_html

ARTICLE_SCHEMA_HINT = (
    '{"title":"文章标题","digest":"120字以内摘要","html":"正文HTML",'
    '"cover_prompt":"封面图提示词或null","tags":["标签"]}'
)


class AiService:
    def __init__(self) -> None:
        self.base_url = (settings.ai_base_url or "").strip().rstrip("/")
        self.api_key = (settings.ai_api_key or "").strip()
        self.model_name = (settings.ai_model_name or "").strip()

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model_name)

    def test_connection(self) -> dict[str, Any]:
        if not self.is_configured():
            raise AiProviderError("AI 未配置，请填写 AI_BASE_URL、AI_API_KEY、AI_MODEL_NAME。")
        content = self._chat_completion(
            "请只返回一个 JSON 对象：{\"title\":\"连通性测试\",\"digest\":\"ok\",\"html\":\"<p>ok</p>\",\"cover_prompt\":null,\"tags\":[\"test\"]}",
            use_response_format=True,
            timeout=30,
            max_tokens=300,
        )
        parsed = _parse_json_object(content)
        return {
            "ok": True,
            "model": self.model_name,
            "base_url": self.base_url,
            "title": parsed.get("title"),
        }

    def polish_markdown(self, markdown: str, instruction: str | None = None) -> AiArticleResult:
        fallback_html = apply_wechat_style(markdown_to_html(markdown))
        if not self.is_configured():
            return AiArticleResult(
                title="未配置 AI 的 Markdown 预览",
                digest="当前仅完成本地 Markdown 转换，配置 AI_BASE_URL、AI_API_KEY、AI_MODEL_NAME 后可启用 AI 润色。",
                html=fallback_html,
                cover_prompt=None,
                tags=[],
            )
        if len(markdown) > 800:
            return self._polish_long_markdown(markdown, fallback_html, instruction)

        prompt = f"""
把下面 Markdown 润色成公众号文章。保留事实，不编造；只生成一篇文章。
输出 JSON，字段必须为 title,digest,html,cover_prompt,tags。
html 只用 p,h2,h3,strong,em,blockquote,ul,ol,li,img,a,pre,code。
图片 img src 原样保留。
用户要求：{instruction or "无"}

Markdown:
{markdown}
"""
        try:
            return self._create_article(prompt, max_tokens=1200, timeout=45)
        except AiProviderError:
            return AiArticleResult(
                title=_guess_title_from_markdown(markdown),
                digest="AI 润色超时，已保留本地 Markdown 转换结果。",
                html=fallback_html,
                cover_prompt=None,
                tags=[],
            )

    def _polish_long_markdown(
        self, markdown: str, fallback_html: str, instruction: str | None
    ) -> AiArticleResult:
        sample = markdown[:2500]
        prompt = f"""
这是一篇较长 Markdown。不要重写全文，只根据开头内容生成文章元数据。
输出 JSON，字段必须为 title,digest,html,cover_prompt,tags。
html 字段固定返回空字符串 ""。
摘要不超过120字。标题自然，不夸张。
用户要求：{instruction or "无"}

Markdown 开头：
{sample}
"""
        try:
            metadata = self._create_article(prompt, max_tokens=800, timeout=45)
            return AiArticleResult(
                title=metadata.title,
                digest=metadata.digest,
                html=fallback_html,
                cover_prompt=metadata.cover_prompt,
                tags=metadata.tags,
            )
        except AiProviderError:
            return AiArticleResult(
                title=_guess_title_from_markdown(markdown),
                digest="AI 润色超时，已保留本地 Markdown 转换结果。",
                html=fallback_html,
                cover_prompt=None,
                tags=[],
            )

    def generate_from_topic(
        self, topic: str, audience: str | None, style: str | None, word_count: int | None
    ) -> AiArticleResult:
        if not self.is_configured():
            html = apply_wechat_style(
                markdown_to_html(
                    f"# {topic}\n\n请配置 AI_BASE_URL、AI_API_KEY、AI_MODEL_NAME 后，让系统根据该主题生成完整公众号文章。"
                )
            )
            return AiArticleResult(
                title=topic,
                digest="AI 模型未配置，已创建占位草稿。",
                html=html,
                cover_prompt=None,
                tags=[],
            )

        target_words = word_count or 1200
        prompt = f"""
请生成一篇公众号文章，只生成一篇，不要生成列表或多个示例。
主题：{topic}
读者：{audience or "普通读者"}
风格：{style or "清晰、专业、自然"}
长度：约{target_words}个中文字。
要求：标题自然；摘要不超过120字；正文用简洁 HTML；不编造数据和来源。
输出 JSON，字段必须为 title,digest,html,cover_prompt,tags。
"""
        token_budget = max(800, min(3000, target_words * 5))
        return self._create_article(prompt, max_tokens=token_budget, timeout=90)

    def _create_article(self, prompt: str, *, max_tokens: int, timeout: int) -> AiArticleResult:
        raw = self._chat_completion(
            prompt, use_response_format=True, timeout=timeout, max_tokens=max_tokens
        )
        try:
            payload = _parse_json_object(raw)
            payload["html"] = apply_wechat_style(sanitize_html(payload["html"]))
            return AiArticleResult.model_validate(payload)
        except (KeyError, json.JSONDecodeError, ValidationError) as exc:
            raise AiProviderError(
                f"AI 返回内容无法解析，请检查模型是否按 JSON 输出。原始返回片段: {raw[:300]}"
            ) from exc

    def _chat_completion(
        self, prompt: str, *, use_response_format: bool, timeout: int, max_tokens: int | None = None
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是公众号文章助手。只返回一个合法 JSON 对象，不要 Markdown 代码块，不要解释。"
                    f"结构：{ARTICLE_SCHEMA_HINT}"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
        }
        if self._should_disable_thinking():
            payload["thinking"] = {"type": "disabled"}
        if max_tokens:
            if self._is_kimi_model():
                payload["max_completion_tokens"] = max_tokens
            else:
                payload["max_tokens"] = max_tokens
        if use_response_format:
            payload["response_format"] = {"type": "json_object"}

        response_payload = self._post_chat_completion(payload, timeout=timeout)
        return _extract_message_content(response_payload)

    def _post_chat_completion(self, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        url = self._chat_completions_url()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise AiProviderError(f"AI 服务连接失败，请检查 AI_BASE_URL: {exc}") from exc

        if response.status_code == 400 and "response_format" in payload:
            fallback_payload = dict(payload)
            fallback_payload.pop("response_format", None)
            return self._post_chat_completion(fallback_payload, timeout=timeout)

        if response.status_code == 401:
            raise AiProviderError("AI API Key 无效或无权限，请检查 AI_API_KEY。")

        if response.status_code >= 400:
            detail = _extract_error_message(response)
            raise AiProviderError(
                f"AI 请求失败 HTTP {response.status_code}，请检查 AI_BASE_URL、AI_MODEL_NAME 和账号权限: {detail}"
            )

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise AiProviderError(f"AI 服务返回的不是 JSON: {response.text[:300]}") from exc

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _should_disable_thinking(self) -> bool:
        model = self.model_name.lower()
        return model.startswith("kimi-k2.6") or model.startswith("kimi-k2.5")

    def _is_kimi_model(self) -> bool:
        model = self.model_name.lower()
        host = self.base_url.lower()
        return model.startswith("kimi-") or "moonshot" in host or "kimi" in host


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not choices:
        raise AiProviderError(f"AI 返回缺少 choices: {str(payload)[:300]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") in ("text", "output_text")
        ]
        text = "".join(text_parts).strip()
        if text:
            return text
    text = choices[0].get("text")
    if isinstance(text, str) and text.strip():
        return text
    raise AiProviderError(f"AI 返回内容为空: {str(payload)[:300]}")


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text[:500]
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(payload)[:500]


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _guess_title_from_markdown(markdown: str) -> str:
    for line in markdown.splitlines():
        text = line.strip()
        if text.startswith("#"):
            return text.lstrip("#").strip()[:100] or "Markdown 文章"
        if text:
            return text[:100]
    return "Markdown 文章"


class AiProviderError(RuntimeError):
    pass
