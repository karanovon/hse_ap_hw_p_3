# Pydantic схемы для валидации запросов и ответов

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field, field_validator
import re


class LinkCreate(BaseModel):
    """
    Схема для создания новой короткой ссылки
    """
    original_url: HttpUrl = Field(..., description="Оригинальный длинный URL")
    custom_alias: Optional[str] = Field(
        None,
        min_length=3, 
        max_length=20,
        description="Кастомный alias для короткой ссылки (только буквы и цифры)"
    )
    expires_at: Optional[datetime] = Field(
        None,
        description="Дата истечения ссылки (опционально)"
    )

    @field_validator('custom_alias')
    def validate_custom_alias(cls, v):
        """Валидация кастомного alias - только буквы и цифры"""
        if v is not None:
            if not re.match("^[a-zA-Z0-9_-]+$", v):
                raise ValueError('Alias может содержать только буквы, цифры, дефис и подчеркивание')
        return v


class LinkUpdate(BaseModel):
    """
    Схема для обновления существующей ссылки
    """
    original_url: HttpUrl = Field(..., description="Новый оригинальный URL")


class LinkResponse(BaseModel):
    """
    Схема ответа с информацией о ссылке
    """
    original_url: str
    short_code: str
    short_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    is_custom: bool

    class Config:
        from_attributes = True


class LinkStatsResponse(BaseModel):
    """
    Схема ответа со статистикой по ссылке
    """
    original_url: str
    short_code: str
    created_at: datetime
    clicks: int
    last_accessed_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class LinkSearchResponse(BaseModel):
    """
    Схема ответа при поиске по оригинальному URL
    """
    original_url: str
    short_code: str
    short_url: str
    created_at: datetime
    clicks: int
