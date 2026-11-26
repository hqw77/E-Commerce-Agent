"""用户账号模型.

users 表保存认证主体和权限标记. 邮箱是登录唯一标识, 密码只保存 Argon2id 哈希,
不保存明文. 用户是否可登录和是否管理员由 is_active/is_admin 控制.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def normalize_email(email: str) -> str:
    """
    Normalize an email address.

    Remove leading and trailing whitespace
    and convert the address to lowercase.

    统一大小写和空白可以避免 Foo@example.com 与 foo@example.com 注册成两个账号.
    """
    return email.strip().lower()


class User(Base):
    """
    User ORM model.

    Represents a registered user in the e-commerce system.

    该模型不保存会话或权限明细, 角色只通过 is_admin 做最小化区分.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # 邮箱是登录唯一标识, 唯一约束同时承担并发注册的业务约束.
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    # 只保存 Argon2id 哈希, 不保存明文或可逆密文.
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 禁用账号时保留历史数据, 但认证依赖会拒绝该用户.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # 最小权限原则: 默认普通用户, 管理端接口依赖 CurrentAdmin 再校验.
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )

    # 调试角色只能访问 Trace/调试接口, 默认不具备业务审批权限.
    is_debugger: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # 仅用于记录行更新时间, 不承担权限或会话语义.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
