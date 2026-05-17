from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    User, Order, OrderStatus, WorkType,
    Payment, PaymentStatus, PaymentType, Revision
)


class UserRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def get_or_create(self, user_id: int, username: str | None, full_name: str) -> User:
        r = await self.s.execute(select(User).where(User.id == user_id))
        user = r.scalar_one_or_none()
        if not user:
            user = User(id=user_id, username=username, full_name=full_name)
            self.s.add(user)
            await self.s.commit()
        return user


class OrderRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def create(
        self,
        user_id: int,
        work_type: WorkType,
        topic: str,
        comment: str | None,
        is_priority: bool,
        free_revisions: int,
    ) -> Order:
        order = Order(
            user_id=user_id,
            work_type=work_type,
            topic=topic,
            comment=comment,
            is_priority=is_priority,
            free_revisions_left=free_revisions,
        )
        self.s.add(order)
        await self.s.commit()
        await self.s.refresh(order)
        return order

    async def get(self, order_id: int) -> Optional[Order]:
        r = await self.s.execute(select(Order).where(Order.id == order_id))
        return r.scalar_one_or_none()

    async def get_queue(self) -> List[Order]:
        """Все заказы в очереди (оплачены, не выполнены). Приоритетные — первые."""
        r = await self.s.execute(
            select(Order)
            .where(Order.status.in_([OrderStatus.PAID, OrderStatus.IN_WORK, OrderStatus.REVISION]))
            .order_by(Order.is_priority.desc(), Order.created_at.asc())
        )
        return r.scalars().all()

    async def get_user_orders(self, user_id: int) -> List[Order]:
        r = await self.s.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
        )
        return r.scalars().all()

    async def set_status(self, order_id: int, status: OrderStatus) -> None:
        await self.s.execute(
            update(Order).where(Order.id == order_id).values(status=status)
        )
        await self.s.commit()

    async def set_queue_message(self, order_id: int, message_id: int) -> None:
        await self.s.execute(
            update(Order).where(Order.id == order_id).values(queue_message_id=message_id)
        )
        await self.s.commit()

    async def set_paid(self, order_id: int) -> None:
        await self.s.execute(
            update(Order).where(Order.id == order_id).values(status=OrderStatus.PAID)
        )
        await self.s.commit()

    async def set_priority(self, order_id: int) -> None:
        await self.s.execute(
            update(Order).where(Order.id == order_id).values(is_priority=True)
        )
        await self.s.commit()

    async def decrement_free_revision(self, order_id: int) -> None:
        r = await self.s.execute(select(Order).where(Order.id == order_id))
        order = r.scalar_one()
        new_free = max(0, order.free_revisions_left - 1)
        new_count = order.revision_count + 1
        await self.s.execute(
            update(Order).where(Order.id == order_id).values(
                free_revisions_left=new_free,
                revision_count=new_count,
                status=OrderStatus.REVISION,
            )
        )
        await self.s.commit()


class RevisionRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def create(
        self,
        order_id: int,
        is_paid: bool,
        comment: str | None,
        file_id: str | None,
    ) -> Revision:
        rev = Revision(order_id=order_id, is_paid=is_paid, comment=comment, file_id=file_id)
        self.s.add(rev)
        await self.s.commit()
        await self.s.refresh(rev)
        return rev

    async def get_by_order(self, order_id: int) -> List[Revision]:
        r = await self.s.execute(
            select(Revision).where(Revision.order_id == order_id).order_by(Revision.created_at)
        )
        return r.scalars().all()


class PaymentRepo:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def create(
        self,
        user_id: int,
        order_id: int,
        payment_type: PaymentType,
        amount: int,
        provider: str = "yukassa",
        currency: str = "RUB",
    ) -> Payment:
        p = Payment(
            user_id=user_id,
            order_id=order_id,
            payment_type=payment_type,
            provider=provider,
            amount=amount,
            currency=currency,
        )
        self.s.add(p)
        await self.s.commit()
        await self.s.refresh(p)
        return p

    async def set_external(self, payment_id: int, external_id: str) -> None:
        await self.s.execute(
            update(Payment).where(Payment.id == payment_id).values(external_id=external_id)
        )
        await self.s.commit()

    async def set_status(self, payment_id: int, status: PaymentStatus) -> None:
        await self.s.execute(
            update(Payment).where(Payment.id == payment_id).values(status=status)
        )
        await self.s.commit()

    async def get_pending_by_order(self, order_id: int, ptype: PaymentType) -> Optional[Payment]:
        r = await self.s.execute(
            select(Payment).where(
                Payment.order_id == order_id,
                Payment.payment_type == ptype,
                Payment.status == PaymentStatus.PENDING,
            )
        )
        return r.scalar_one_or_none()
