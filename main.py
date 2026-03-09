# Точка входа FastAPI приложения и управление жизненным циклом.

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, status
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from api.database import engine, init_db, AsyncSessionLocal
from api.middleware import RequestLoggingMiddleware
from api.routers import links

# Создаем планировщик для удаления просроченных ссылок
scheduler = AsyncIOScheduler()


async def cleanup_expired_links():
    """
    Фоновая задача для удаления истекших ссылок
    Запускается каждую минуту
    """
    from api.models import Link
    from sqlalchemy import delete

    db = AsyncSessionLocal()
    try:
        current_time = datetime.now(timezone.utc)
        # Находим и удаляем все истекшие ссылки
        stmt = delete(Link).where(Link.expires_at < current_time)
        result = await db.execute(stmt)
        await db.commit()

        if result.rowcount > 0:
            print(f"Очистка: удалено {result.rowcount} истекших ссылок в {current_time}")
    except Exception as e:
        print(f"Ошибка при очистке истекших ссылок: {e}")
        await db.rollback()
    finally:
        await db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Контекст жизненного цикла для событий запуска/остановки приложения
    """
    print("Запуск URL Shortener Service")

    # Инициализируем базу данных
    await init_db()
    print("База данных инициализирована")

    # Запускаем планировщик для очистки истекших ссылок
    scheduler.add_job(
        cleanup_expired_links,
        trigger=IntervalTrigger(minutes=1),
        id="cleanup_expired_links",
        replace_existing=True
    )
    scheduler.start()
    print("Планировщик очистки истекших ссылок запущен")

    yield  # Приложение работает здесь

    # События при остановке приложения
    scheduler.shutdown()
    print("Планировщик остановлен")

    await engine.dispose()
    print("Соединение с базой данных закрыто")
    print("Приложение остановлено")


# Создаем FastAPI приложение
app = FastAPI(
    title="URL Shortener Service",
    description="Сервис для создания коротких ссылок с аналитикой и управлением",
    version="1.0.0",
    lifespan=lifespan
)


# Добавляем middleware для логирования запросов
app.add_middleware(RequestLoggingMiddleware)


@app.get("/", tags=["Root"])
async def root():
    """
    Корневой эндпоинт - базовый GET запрос
    """
    return {
        "message": "URL Shortener Service",
        "version": "1.0.0",
        "endpoints": {
            "create_short_link": {
                "method": "POST",
                "path": "/links/shorten",
                "description": "Создать короткую ссылку (с опциональным кастомным alias и сроком действия)"
            },
            "redirect_to_original": {
                "method": "GET",
                "path": "/links/{short_code}",
                "description": "Перенаправление на оригинальный URL"
            },
            "get_link_info": {
                "method": "GET",
                "path": "/links/{short_code}/info",
                "description": "Получить информацию о короткой ссылке"
            },
            "update_link": {
                "method": "PUT",
                "path": "/links/{short_code}",
                "description": "Обновить оригинальный URL для короткой ссылки"
            },
            "delete_link": {
                "method": "DELETE",
                "path": "/links/{short_code}",
                "description": "Удалить короткую ссылку"
            },
            "get_stats": {
                "method": "GET",
                "path": "/links/{short_code}/stats",
                "description": "Получить статистику по ссылке"
            },
            "search_by_original_url": {
                "method": "GET",
                "path": "/links/search",
                "description": "Поиск ссылок по оригинальному URL"
            }
        },
        "database": {
            "type": "SQLite (асинхронная)",
            "file": "url_shortener.db"
        }
    }


@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check():
    """
    Эндпоинт проверки здоровья приложения
    """
    return {
        "status": "healthy",
        "service": "url-shortener-service",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Регистрируем роутер для работы со ссылками
app.include_router(links.router, prefix="/links")
