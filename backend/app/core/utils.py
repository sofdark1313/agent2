"""
公共工具函数
"""


def guess_title_from_markdown(markdown: str, max_length: int = 100) -> str:
    """
    从 Markdown 内容猜测标题
    
    Args:
        markdown: Markdown 文本
        max_length: 标题最大长度
    
    Returns:
        猜测的标题
    """
    for line in markdown.splitlines():
        text = line.strip()
        if text.startswith("#"):
            title = text.lstrip("#").strip()
            if title:
                return title[:max_length]
        if text:
            return text[:max_length]
    return "Markdown 文章"


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    截断文本
    
    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀
    
    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
