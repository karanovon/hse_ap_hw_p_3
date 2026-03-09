# Роутер для работы с короткими ссылками
# Содержит все эндпоинты для создания, управления и аналитики ссылок

import secrets
import string
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi.responses import RedirectResponse

from api.database import get_db
from api import models, schemas

router = APIRouter(tags=["links"])

DEFAULT_CODE_LENGTH = 6
ALPHABET = string.ascii_letters + string.digits


def generate_short_code(length: int = DEFAULT_CODE_LENGTH) -> str:
    """
    Генерирует случайный короткий код заданной длины
    """
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))


async def get_link_by_code(
    db: AsyncSession,
    short_code: str,
    increment_clicks: bool = False
) -> Optional[models.Link]:
    """
    Вспомогательная функция для получения ссылки по коду
    Опционально увеличивает счетчик кликов
    """
    result = await db.execute(
        select(models.Link).where(models.Link.short_code == short_code)
    )
    link = result.scalar_one_or_none()

    if link and increment_clicks:
        link.clicks += 1
        link.last_accessed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(link)

    return link


@router.post("/shorten", response_model=schemas.LinkResponse, status_code=status.HTTP_201_CREATED)
async def create_short_link(
    request: Request,
    link_data: schemas.LinkCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Создает короткую ссылку

    - Если передан custom_alias, проверяет его уникальность
    - Если передан expires_at, устанавливает срок действия ссылки
    - Возвращает созданную короткую ссылку
    """
    # Определяем короткий код
    short_code = link_data.custom_alias

    if short_code:
        # Проверяем уникальность кастомного alias
        existing = await get_link_by_code(db, short_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Такой alias уже существует"
            )
    else:
        # Генерируем уникальный случайный код
        for _ in range(10):  # Пробуем до 10 раз
            short_code = generate_short_code()
            existing = await get_link_by_code(db, short_code)
            if not existing:
                break
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось сгенерировать уникальный код"
            )

    # Создаем новую ссылку
    new_link = models.Link(
        original_url=str(link_data.original_url),
        short_code=short_code,
        custom_alias=bool(link_data.custom_alias),
        expires_at=link_data.expires_at
    )

    try:
        db.add(new_link)
        await db.commit()
        await db.refresh(new_link)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка при создании ссылки"
        )

    # Формируем полный короткий URL
    base_url = str(request.base_url).rstrip('/')
    short_url = f"{base_url}/links/{short_code}"

    return schemas.LinkResponse(
        original_url=new_link.original_url,
        short_code=new_link.short_code,
        short_url=short_url,
        created_at=new_link.created_at,
        expires_at=new_link.expires_at,
        is_custom=new_link.custom_alias
    )


@router.get("/{short_code}")
async def redirect_to_original(
    short_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Перенаправляет на оригинальный URL по короткому коду
    Увеличивает счетчик кликов
    """
    link = await get_link_by_code(db, short_code, increment_clicks=True)

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена"
        )

    # Проверяем, не истекла ли ссылка
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Срок действия ссылки истек"
        )

    return RedirectResponse(url=link.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/{short_code}/info", response_model=schemas.LinkResponse)
async def get_link_info(
    short_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Возвращает информацию о короткой ссылке (без перенаправления)
    """
    link = await get_link_by_code(db, short_code)

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена"
        )

    return schemas.LinkResponse(
        original_url=link.original_url,
        short_code=link.short_code,
        short_url=f"/links/{short_code}",
        created_at=link.created_at,
        expires_at=link.expires_at,
        is_custom=link.custom_alias
    )


@router.put("/{short_code}", response_model=schemas.LinkResponse)
async def update_link(
    short_code: str,
    link_data: schemas.LinkUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Обновляет оригинальный URL для существующей короткой ссылки
    """
    link = await get_link_by_code(db, short_code)

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена"
        )

    link.original_url = str(link_data.original_url)
    await db.commit()
    await db.refresh(link)

    return schemas.LinkResponse(
        original_url=link.original_url,
        short_code=link.short_code,
        short_url=f"/links/{short_code}",
        created_at=link.created_at,
        expires_at=link.expires_at,
        is_custom=link.custom_alias
    )


@router.delete("/{short_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    short_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Удаляет короткую ссылку
    """
    result = await db.execute(
        delete(models.Link).where(models.Link.short_code == short_code)
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена"
        )

    await db.commit()
    return None


@router.get("/{short_code}/stats", response_model=schemas.LinkStatsResponse)
async def get_link_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Возвращает статистику по ссылке:
    - Оригинальный URL
    - Дата создания
    - Количество переходов
    - Дата последнего использования
    """
    link = await get_link_by_code(db, short_code)

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена"
        )

    return schemas.LinkStatsResponse(
        original_url=link.original_url,
        short_code=link.short_code,
        created_at=link.created_at,
        clicks=link.clicks,
        last_accessed_at=link.last_accessed_at,
        expires_at=link.expires_at
    )


@router.get("/search", response_model=List[schemas.LinkSearchResponse])
async def search_by_original_url(
    original_url: str = Query(..., description="Оригинальный URL для поиска"),
    db: AsyncSession = Depends(get_db)
):
    """
    Поиск коротких ссылок по оригинальному URL
    Возвращает все ссылки, созданные для данного URL
    """
    result = await db.execute(
        select(models.Link).where(models.Link.original_url == original_url)
    )
    links = result.scalars().all()

    return [
        schemas.LinkSearchResponse(
            original_url=link.original_url,
            short_code=link.short_code,
            short_url=f"/links/{link.short_code}",
            created_at=link.created_at,
            clicks=link.clicks
        )
        for link in links
    ]
