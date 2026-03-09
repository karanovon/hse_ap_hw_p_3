# Определение моделей базы данных SQLAlchemy

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Index

from api.database import Base


class Link(Base):
    """
    Модель для хранения информации о коротких ссылках
    """
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    original_url = Column(String, nullable=False, index=True)
    short_code = Column(String, unique=True, index=True, nullable=False)
    custom_alias = Column(Boolean, default=False)

    clicks = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)

    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_links_expires_at', 'expires_at'),
    )
