"""SQLAlchemy 声明式模型基类.

所有 ORM 模型继承同一个 Base, Alembic 才能从一个 metadata 中发现全部表.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.

    All database models should inherit from this class.

    只定义声明式基类, 不在这里放业务字段或通用 mixin.
    """