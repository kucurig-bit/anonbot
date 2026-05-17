from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    work_type  = State()   # выбор типа работы
    topic      = State()   # ввод темы
    comment    = State()   # доп. требования (опционально)
    priority   = State()   # предложение приоритета
    paying     = State()   # ожидание оплаты заказа


class RevisionForm(StatesGroup):
    entering   = State()   # пользователь вводит текст/файл правки
    paying     = State()   # ожидание оплаты правки (если платная)


class AdminForm(StatesGroup):
    uploading_file  = State()   # админ загружает готовый файл для заказа
