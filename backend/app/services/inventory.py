"""库存业务 Service.

文件职责:
- 管理总库存, 预占量和库存流水.
- 为订单提供预占, 释放, 发货扣减.
- 为售后和手工调整提供入库/出库.
- 通过幂等键和原子 UPDATE 处理并发.

核心边界:
InventoryRepository 只执行 SQL; 本 Service 负责业务校验,
事务边界和流水一致性.
"""

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
    ValidationException,
)
from app.models.inventory import Inventory
from app.models.inventory_transaction import InventoryTransaction
from app.repositories.inventory import InventoryRepository
from app.repositories.inventory_transaction import (
    InventoryTransactionRepository,
)
from app.services.transaction import transaction_context


@dataclass(frozen=True)
class InventoryOperationResult:
    """一次库存变更的结果.

    Args:
        transaction: 新写入的库存流水.
        inventory: 变更后的库存行.
    """

    transaction: InventoryTransaction
    inventory: Inventory


class InventoryService:
    """库存操作和流水的业务规则."""

    def __init__(self, session: AsyncSession) -> None:
        """绑定当前请求 session 和库存 Repository."""
        self.session = session
        self.repository = InventoryRepository(session)
        self.transaction_repository = InventoryTransactionRepository(session)

    @staticmethod
    def _available(inventory: Inventory) -> int:
        """计算可用库存 = 总量 - 预占量."""
        return inventory.total_quantity - inventory.reserved_quantity

    @staticmethod
    def _same_fingerprint(
        transaction: InventoryTransaction,
        *,
        sku_id: int,
        transaction_type: str,
        total_delta: int,
        reserved_delta: int,
        business_type: str,
    ) -> bool:
        """判断已存在流水是否与本次幂等请求完全一致."""
        return (
            transaction.sku_id == sku_id
            and transaction.transaction_type == transaction_type
            and transaction.total_delta == total_delta
            and transaction.reserved_delta == reserved_delta
            and transaction.business_type == business_type
            and transaction.business_id is None
            and transaction.business_item_id is None
        )

    async def _existing_result(
        self,
        transaction: InventoryTransaction,
        *,
        sku_id: int,
        transaction_type: str,
        total_delta: int,
        reserved_delta: int,
        business_type: str,
    ) -> InventoryOperationResult:
        """复用已存在流水; 参数不一致时返回幂等冲突."""
        if not self._same_fingerprint(
            transaction,
            sku_id=sku_id,
            transaction_type=transaction_type,
            total_delta=total_delta,
            reserved_delta=reserved_delta,
            business_type=business_type,
        ):
            raise ConflictException(
                message="Idempotency key was used with different parameters",
                code="IDEMPOTENCY_KEY_CONFLICT",
            )

        inventory = await self.repository.get_by_sku_id(sku_id)

        if inventory is None:
            raise ResourceNotFoundException(
                message="Inventory not found",
                code="INVENTORY_NOT_FOUND",
            )

        return InventoryOperationResult(
            transaction=transaction,
            inventory=inventory,
        )

    async def get_inventory(self, sku_id: int) -> Inventory:
        """读取库存, 不存在时抛 404."""
        inventory = await self.repository.get_by_sku_id(sku_id)

        if inventory is None:
            raise ResourceNotFoundException(
                message="Inventory not found",
                code="INVENTORY_NOT_FOUND",
            )

        return inventory

    async def list_transactions(
        self,
        sku_id: int,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[InventoryTransaction], int]:
        """分页读取 SKU 的库存流水."""
        if await self.repository.get_by_sku_id(sku_id) is None:
            raise ResourceNotFoundException(
                message="Inventory not found",
                code="INVENTORY_NOT_FOUND",
            )

        items = await self.transaction_repository.list_by_sku(
            sku_id,
            page=page,
            page_size=page_size,
        )
        total = await self.transaction_repository.count_by_sku(sku_id)
        return items, total

    async def _execute(
        self,
        *,
        sku_id: int,
        transaction_type: str,
        total_delta: int,
        reserved_delta: int,
        business_type: str,
        idempotency_key: str,
        operator_id: int | None,
        remark: str | None,
        absolute: int | None = None,
        require_available: int | None = None,
        require_initial: bool = False,
    ) -> InventoryOperationResult:
        """执行一次带幂等和行锁的库存变更.

        Returns:
            库存流水和变更后的库存.

        Raises:
            ConflictException: 幂等冲突, 并发死锁或可用库存不足.
            ResourceNotFoundException: 库存不存在.
        """
        # ① 先做一次无锁幂等查询, 命中就直接复用.
        existing = await self.transaction_repository.get_by_key(idempotency_key)

        if existing is not None:
            return await self._existing_result(
                existing,
                sku_id=sku_id,
                transaction_type=transaction_type,
                total_delta=total_delta,
                reserved_delta=reserved_delta,
                business_type=business_type,
            )

        try:
            async with transaction_context(self.session):
                # ② 锁库存行后再次查幂等流水, 避免 REPEATABLE READ 下漏看并发提交.
                inventory = await self.repository.get_by_sku_id_for_update(sku_id)

                if inventory is None:
                    raise ResourceNotFoundException(
                        message="Inventory not found",
                        code="INVENTORY_NOT_FOUND",
                    )

                # Recheck after obtaining the inventory row lock. A plain
                # SELECT in REPEATABLE READ may miss a concurrently
                # committed ledger row.
                existing = await self.transaction_repository.get_by_key(
                    idempotency_key,
                    for_update=True,
                )

                if existing is not None:
                    return await self._existing_result(
                        existing,
                        sku_id=sku_id,
                        transaction_type=transaction_type,
                        total_delta=total_delta,
                        reserved_delta=reserved_delta,
                        business_type=business_type,
                    )

                if require_initial and (
                    inventory.total_quantity != 0
                    or inventory.reserved_quantity != 0
                    or await self.transaction_repository.exists_for_sku(sku_id)
                ):
                    raise ConflictException(
                        message="Inventory has already been initialized",
                        code="INVENTORY_ALREADY_INITIALIZED",
                    )

                rowcount = await self.repository.update_total(
                    sku_id,
                    delta=total_delta,
                    absolute=absolute,
                    require_available=require_available,
                )

                # ③ rowcount 为 0 表示库存不足或初始化条件不满足.
                if rowcount != 1:
                    if require_initial:
                        raise ConflictException(
                            message="Inventory has already been initialized",
                            code="INVENTORY_ALREADY_INITIALIZED",
                        )

                    raise ConflictException(
                        message="Insufficient available inventory",
                        code="INSUFFICIENT_STOCK",
                    )

                await self.session.refresh(inventory)
                # ④ 库存更新成功后写入流水, 保存变更前后数量.
                transaction = await self.transaction_repository.create(
                    sku_id=sku_id,
                    transaction_type=transaction_type,
                    total_delta=total_delta,
                    reserved_delta=reserved_delta,
                    total_after=inventory.total_quantity,
                    reserved_after=inventory.reserved_quantity,
                    idempotency_key=idempotency_key,
                    business_type=business_type,
                    operator_id=operator_id,
                    remark=remark,
                )

                return InventoryOperationResult(
                    transaction=transaction,
                    inventory=inventory,
                )

        except (IntegrityError, OperationalError) as exc:
            # ⑤ 唯一键冲突或死锁时回滚, 按幂等键重新读取已存在流水.
            is_idempotency_conflict = isinstance(
                exc, IntegrityError
            ) and "uq_inventory_transactions_idempotency" in str(exc.orig)
            orig_args = (
                getattr(exc.orig, "args", None)
                if isinstance(exc, OperationalError)
                else None
            )
            deadlock_code = orig_args[0] if orig_args else None
            is_deadlock = deadlock_code in {1213, 1205}

            if not is_idempotency_conflict and not is_deadlock:
                raise

            await self.session.rollback()
            existing = await self.transaction_repository.get_by_key(idempotency_key)

            if existing is None:
                if is_deadlock:
                    raise ConflictException(
                        message="Concurrent inventory operation conflict",
                        code="IDEMPOTENCY_KEY_CONFLICT",
                    ) from exc

                raise

            return await self._existing_result(
                existing,
                sku_id=sku_id,
                transaction_type=transaction_type,
                total_delta=total_delta,
                reserved_delta=reserved_delta,
                business_type=business_type,
            )

    async def initialize(
        self,
        *,
        sku_id: int,
        initial_total: int,
        idempotency_key: str,
        operator_id: int | None,
        remark: str | None,
    ) -> InventoryOperationResult:
        """首次初始化库存, 要求当前库存和流水都为空."""
        if initial_total <= 0:
            raise ValidationException(
                message="Initial stock must be greater than zero",
                code="INVALID_QUANTITY",
            )

        return await self._execute(
            sku_id=sku_id,
            transaction_type="INITIAL",
            total_delta=initial_total,
            reserved_delta=0,
            business_type="INITIAL",
            idempotency_key=idempotency_key,
            operator_id=operator_id,
            remark=remark,
            absolute=initial_total,
            require_initial=True,
        )

    async def stock_in(
        self,
        *,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        operator_id: int | None,
        remark: str | None,
    ) -> InventoryOperationResult:
        """手工入库, 增加总库存并写流水."""
        if quantity <= 0:
            raise ValidationException(
                message="Stock-in quantity must be greater than zero",
                code="INVALID_QUANTITY",
            )

        return await self._execute(
            sku_id=sku_id,
            transaction_type="STOCK_IN",
            total_delta=quantity,
            reserved_delta=0,
            business_type="MANUAL",
            idempotency_key=idempotency_key,
            operator_id=operator_id,
            remark=remark,
        )

    async def direct_outbound(
        self,
        *,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        operator_id: int | None,
        remark: str | None,
    ) -> InventoryOperationResult:
        """手工出库, 直接从可用库存扣减."""
        if quantity <= 0:
            raise ValidationException(
                message="Outbound quantity must be greater than zero",
                code="INVALID_QUANTITY",
            )

        return await self._execute(
            sku_id=sku_id,
            transaction_type="DIRECT_OUTBOUND",
            total_delta=-quantity,
            reserved_delta=0,
            business_type="MANUAL",
            idempotency_key=idempotency_key,
            operator_id=operator_id,
            remark=remark,
            require_available=quantity,
        )

    async def adjust(
        self,
        *,
        sku_id: int,
        quantity_delta: int,
        idempotency_key: str,
        operator_id: int | None,
        remark: str | None,
    ) -> InventoryOperationResult:
        """按增量调整总库存, 正负均可, 但不能为零."""
        if quantity_delta == 0:
            raise ValidationException(
                message="Adjustment delta must not be zero",
                code="INVALID_QUANTITY",
            )

        return await self._execute(
            sku_id=sku_id,
            transaction_type="ADJUSTMENT",
            total_delta=quantity_delta,
            reserved_delta=0,
            business_type="MANUAL",
            idempotency_key=idempotency_key,
            operator_id=operator_id,
            remark=remark,
        )

    async def _locked_inventory(self, sku_id: int) -> Inventory:
        """锁定库存行, 不存在时抛 404."""
        inventory = await self.repository.get_by_sku_id_for_update(sku_id)
        if inventory is None:
            raise ResourceNotFoundException(
                message="Inventory not found",
                code="INVENTORY_NOT_FOUND",
            )
        return inventory

    async def _ledger(
        self,
        *,
        sku_id: int,
        transaction_type: str,
        total_delta: int,
        reserved_delta: int,
        idempotency_key: str,
        business_type: str,
        business_id: int | None,
        business_item_id: int | None,
        operator_id: int | None,
        remark: str | None,
    ) -> InventoryTransaction:
        """在已锁库存的基础上写入一条流水."""
        inventory = await self._locked_inventory(sku_id)
        await self.session.refresh(inventory)
        return await self.transaction_repository.create(
            sku_id=sku_id,
            transaction_type=transaction_type,
            total_delta=total_delta,
            reserved_delta=reserved_delta,
            total_after=inventory.total_quantity,
            reserved_after=inventory.reserved_quantity,
            idempotency_key=idempotency_key,
            business_type=business_type,
            business_id=business_id,
            business_item_id=business_item_id,
            operator_id=operator_id,
            remark=remark,
        )

    async def reserve(
        self,
        *,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        business_type: str,
        business_id: int,
        business_item_id: int | None,
        operator_id: int | None = None,
        remark: str | None = None,
    ) -> InventoryTransaction:
        """在调用方事务内预占库存, 返回库存流水."""
        if quantity <= 0:
            raise ValidationException(
                message="Reserve quantity must be greater than zero",
                code="INVALID_QUANTITY",
            )

        await self._locked_inventory(sku_id)
        rowcount = await self.repository.reserve(sku_id, quantity)
        if rowcount != 1:
            raise ConflictException(
                message="Insufficient available inventory",
                code="INSUFFICIENT_STOCK",
            )

        return await self._ledger(
            sku_id=sku_id,
            transaction_type="RESERVE",
            total_delta=0,
            reserved_delta=quantity,
            idempotency_key=idempotency_key,
            business_type=business_type,
            business_id=business_id,
            business_item_id=business_item_id,
            operator_id=operator_id,
            remark=remark,
        )

    async def release(
        self,
        *,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        business_type: str,
        business_id: int,
        business_item_id: int | None,
        operator_id: int | None = None,
        remark: str | None = None,
    ) -> InventoryTransaction:
        """在调用方事务内释放预占, 返回库存流水."""
        if quantity <= 0:
            raise ValidationException(
                message="Release quantity must be greater than zero",
                code="INVALID_QUANTITY",
            )

        await self._locked_inventory(sku_id)
        rowcount = await self.repository.release(sku_id, quantity)
        if rowcount != 1:
            raise ConflictException(
                message="Reserved inventory is insufficient",
                code="ORDER_ITEM_RESERVATION_MISMATCH",
            )

        return await self._ledger(
            sku_id=sku_id,
            transaction_type="RELEASE",
            total_delta=0,
            reserved_delta=-quantity,
            idempotency_key=idempotency_key,
            business_type=business_type,
            business_id=business_id,
            business_item_id=business_item_id,
            operator_id=operator_id,
            remark=remark,
        )

    async def deduct_reserved(
        self,
        *,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        business_type: str,
        business_id: int,
        business_item_id: int | None,
        operator_id: int | None = None,
        remark: str | None = None,
    ) -> InventoryTransaction:
        """把预占转为实际出库, 同时扣减总量和预占量."""
        if quantity <= 0:
            raise ValidationException(
                message="Outbound quantity must be greater than zero",
                code="INVALID_QUANTITY",
            )

        await self._locked_inventory(sku_id)
        rowcount = await self.repository.deduct_reserved(sku_id, quantity)
        if rowcount != 1:
            raise ConflictException(
                message="Reserved inventory is insufficient",
                code="ORDER_ITEM_RESERVATION_MISMATCH",
            )

        return await self._ledger(
            sku_id=sku_id,
            transaction_type="RESERVED_OUTBOUND",
            total_delta=-quantity,
            reserved_delta=-quantity,
            idempotency_key=idempotency_key,
            business_type=business_type,
            business_id=business_id,
            business_item_id=business_item_id,
            operator_id=operator_id,
            remark=remark,
        )

    async def restock(
        self,
        *,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        business_type: str,
        business_id: int,
        business_item_id: int | None,
        operator_id: int | None = None,
        remark: str | None = None,
    ) -> InventoryTransaction:
        """在调用方事务内增加总库存, 用于退货入库."""
        if quantity <= 0:
            raise ValidationException(
                message="Restock quantity must be greater than zero",
                code="INVALID_QUANTITY",
            )

        await self._locked_inventory(sku_id)
        rowcount = await self.repository.restock(sku_id, quantity)
        if rowcount != 1:
            raise ResourceNotFoundException(
                message="Inventory not found",
                code="INVENTORY_NOT_FOUND",
            )

        return await self._ledger(
            sku_id=sku_id,
            transaction_type="STOCK_IN",
            total_delta=quantity,
            reserved_delta=0,
            idempotency_key=idempotency_key,
            business_type=business_type,
            business_id=business_id,
            business_item_id=business_item_id,
            operator_id=operator_id,
            remark=remark,
        )

    async def direct_outbound_for_business(
        self,
        *,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        business_type: str,
        business_id: int,
        business_item_id: int | None,
        operator_id: int | None = None,
        remark: str | None = None,
    ) -> InventoryTransaction:
        """在调用方事务内直接从可用库存出库."""
        if quantity <= 0:
            raise ValidationException(
                message="Outbound quantity must be greater than zero",
                code="INVALID_QUANTITY",
            )

        await self._locked_inventory(sku_id)
        rowcount = await self.repository.direct_outbound(sku_id, quantity)
        if rowcount != 1:
            raise ConflictException(
                message="Insufficient available inventory",
                code="INSUFFICIENT_STOCK",
            )

        return await self._ledger(
            sku_id=sku_id,
            transaction_type="DIRECT_OUTBOUND",
            total_delta=-quantity,
            reserved_delta=0,
            idempotency_key=idempotency_key,
            business_type=business_type,
            business_id=business_id,
            business_item_id=business_item_id,
            operator_id=operator_id,
            remark=remark,
        )
