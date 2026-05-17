from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    Enum, BigInteger, ForeignKey, Boolean
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Перечисления ──────────────────────────────────────────

class WorkType(str, PyEnum):
    ESSAY     = "essay"
    REFERAT   = "referat"
    KURSOVAYA = "kursovaya"


class OrderStatus(str, PyEnum):
    NEW         = "new"          # только создан, ожидает оплаты
    PAID        = "paid"         # оплачен, попал в очередь
    IN_WORK     = "in_work"      # взят в работу админом
    DONE        = "done"         # выполнен, файл отправлен клиенту
    REVISION    = "revision"     # на доработке (правки)
    CANCELLED   = "cancelled"


class PaymentStatus(str, PyEnum):
    PENDING   = "pending"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"


class PaymentType(str, PyEnum):
    ORDER    = "order"     # оплата самого заказа
    REVISION = "revision"  # оплата правки
    PRIORITY = "priority"  # доплата за приоритет


# ── Таблицы ───────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id        = Column(BigInteger, primary_key=True)   # Telegram user_id
    username  = Column(String(64),  nullable=True)
    full_name = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    orders   = relationship("Order",   back_populates="user")
    payments = relationship("Payment", back_populates="user")


class Order(Base):
    __tablename__ = "orders"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(BigInteger, ForeignKey("users.id"), nullable=False)

    work_type    = Column(Enum(WorkType), nullable=False)
    topic        = Column(Text, nullable=False)         # тема, написанная пользователем
    comment      = Column(Text, nullable=True)          # доп. требования
    is_priority  = Column(Boolean, default=False)       # приоритетная очередь

    status       = Column(Enum(OrderStatus), default=OrderStatus.NEW)

    # Правки
    free_revisions_left = Column(Integer, default=1)   # сколько бесплатных ещё есть
    revision_count      = Column(Integer, default=0)   # всего правок сделано

    # Связка с admin-сообщением в очереди
    queue_message_id    = Column(BigInteger, nullable=True)  # ID сообщения очереди (обновляемое)

    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user      = relationship("User",     back_populates="orders")
    payments  = relationship("Payment",  back_populates="order")
    revisions = relationship("Revision", back_populates="order")


class Revision(Base):
    """Каждая правка по заказу."""
    __tablename__ = "revisions"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    order_id   = Column(Integer, ForeignKey("orders.id"), nullable=False)
    is_paid    = Column(Boolean, default=False)        # False = бесплатная
    comment    = Column(Text, nullable=True)           # текст правки от пользователя
    file_id    = Column(String(256), nullable=True)    # file_id документа от пользователя
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="revisions")


class Payment(Base):
    __tablename__ = "payments"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    order_id       = Column(Integer,    ForeignKey("orders.id"), nullable=True)

    payment_type   = Column(Enum(PaymentType), nullable=False)
    provider       = Column(String(32), default="yukassa")   # yukassa | stars
    amount         = Column(Integer, nullable=False)         # рубли (или Stars)
    currency       = Column(String(8), default="RUB")

    external_id    = Column(String(128), nullable=True)      # ID платежа в ЮКассе
    status         = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)

    created_at     = Column(DateTime, default=datetime.utcnow)

    user  = relationship("User",  back_populates="payments")
    order = relationship("Order", back_populates="payments")
