"""
文件处理和验证工具
"""
import os
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import FileValidationError


def validate_upload_file(file: UploadFile, *, allowed_extensions: list[str] | None = None) -> None:
    """
    验证上传的文件
    
    Args:
        file: 上传的文件
        allowed_extensions: 允许的扩展名列表，默认使用配置中的图片扩展名
    
    Raises:
        FileValidationError: 文件验证失败
    """
    if not file.filename:
        raise FileValidationError("文件名不能为空")
    
    # 验证文件扩展名
    extensions = allowed_extensions or settings.allowed_extensions_list
    ext = Path(file.filename).suffix.lower()
    if ext not in extensions:
        raise FileValidationError(
            f"不支持的文件类型 {ext}，允许的类型：{', '.join(extensions)}",
            filename=file.filename,
        )
    
    # 验证文件大小（如果可以获取）
    if file.size is not None and file.size > settings.max_upload_size_bytes:
        raise FileValidationError(
            f"文件大小超过限制（最大 {settings.max_upload_size_mb}MB）",
            filename=file.filename,
        )


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，防止路径遍历攻击
    
    Args:
        filename: 原始文件名
    
    Returns:
        安全的文件名
    """
    # 只保留文件名部分，去除路径
    filename = os.path.basename(filename)
    
    # 移除危险字符
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    
    # 如果文件名为空或只有扩展名，生成随机名称
    name, ext = os.path.splitext(filename)
    if not name or name.startswith('.'):
        name = uuid.uuid4().hex[:8]
    
    return f"{name}{ext}"


def generate_unique_filename(original_filename: str, prefix: str = "") -> str:
    """
    生成唯一的文件名
    
    Args:
        original_filename: 原始文件名
        prefix: 文件名前缀
    
    Returns:
        唯一的文件名
    """
    ext = Path(original_filename).suffix.lower() or ".jpg"
    unique_id = uuid.uuid4().hex[:12]
    if prefix:
        return f"{prefix}_{unique_id}{ext}"
    return f"{unique_id}{ext}"


async def save_upload_file(
    file: UploadFile,
    upload_dir: Path,
    *,
    validate: bool = True,
    unique_name: bool = True,
) -> Path:
    """
    保存上传的文件
    
    Args:
        file: 上传的文件
        upload_dir: 上传目录
        validate: 是否验证文件
        unique_name: 是否生成唯一文件名
    
    Returns:
        保存后的文件路径
    
    Raises:
        FileValidationError: 文件验证失败
    """
    if validate:
        validate_upload_file(file)
    
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    if unique_name:
        filename = generate_unique_filename(file.filename or "upload.jpg")
    else:
        filename = sanitize_filename(file.filename or "upload.jpg")
    
    destination = upload_dir / filename
    
    # 读取并保存文件内容
    content = await file.read()
    
    # 再次检查实际大小
    if len(content) > settings.max_upload_size_bytes:
        raise FileValidationError(
            f"文件大小超过限制（最大 {settings.max_upload_size_mb}MB）",
            filename=file.filename,
        )
    
    destination.write_bytes(content)
    return destination
