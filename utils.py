import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def extract_structured_data(text: str, prefix: str) -> Optional[str]:
    """
    Извлекает строку данных после заданного префикса.
    Ищет как в начале строки, так и внутри текста.
    """
    pattern = rf"{prefix}\s*(.*)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).split('\n')[0].strip()
    return None

def parse_pipe_data(data_str: str, expected_count: int) -> Optional[list]:
    """
    Разбивает строку по разделителю '|' и проверяет количество элементов.
    """
    if not data_str:
        return None
    
    parts = [p.strip() for p in data_str.split('|')]
    if len(parts) >= expected_count:
        return parts[:expected_count]
    
    logger.warning(f"Expected {expected_count} parts, but got {len(parts)} in: {data_str}")
    return None

def clean_llm_reply(full_reply: str, prefixes: list) -> str:
    """
    Удаляет технические строки с префиксами из ответа для пользователя.
    """
    lines = full_reply.split('\n')
    clean_lines = []
    for line in lines:
        if not any(line.strip().upper().startswith(p.upper()) for p in prefixes):
            clean_lines.append(line)
    
    return '\n'.join(clean_lines).strip()
