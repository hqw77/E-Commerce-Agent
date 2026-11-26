"""ORM 模型聚合导出.

集中导入全部模型, 确保 SQLAlchemy metadata 和 Alembic 能发现所有表.
业务代码应从 app.models 导入, 而不是逐个导入模块文件.
"""

from app.models.after_sale import AfterSale
from app.models.agent_approval import AgentApproval
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.inventory_transaction import InventoryTransaction
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.refresh_session import RefreshSession
from app.models.sku import Sku
from app.models.user import User

__all__ = [
    "AfterSale",
    "AgentApproval",
    "Category",
    "Inventory",
    "InventoryTransaction",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeDocumentVersion",
    "Order",
    "OrderItem",
    "Product",
    "RefreshSession",
    "Sku",
    "User",
]
