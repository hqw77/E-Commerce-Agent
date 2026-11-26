"""SQLAlchemy 声明式模型基类.

所有 ORM 模型继承同一个 Base, Alembic 才能从一个 metadata 中发现全部表.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类.

    不在这里放业务字段或通用 mixin, 避免所有表被动继承无关列.
    """