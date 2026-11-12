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
    """Result of an inventory-changing operation."""

    transaction: InventoryTransaction
    inventory: Inventory


class InventoryService:
    """Business rules for inventory operations and ledger entries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = InventoryRepository(session)
        self.transaction_repository = InventoryTransactionRepository(session)

    @staticmethod
    def _available(inventory: Inventory) -> int:
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
