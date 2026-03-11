import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
import gspread
from google.oauth2.service_account import Credentials
import json

# Загрузка переменных окружения из .env файла (для локальной разработки)
try:
    from dotenv import load_dotenv

    load_dotenv()
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("Переменные окружения загружены из .env файла")
except ImportError:
    pass

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(CHOOSING_ACTION, ADD_ADDRESS, EDIT_ADDRESS, DELETE_ADDRESS,
 ADD_ORDER, SELECT_ADDRESS, SELECT_PRODUCT, ENTER_QUANTITY, ENTER_DELIVERY_DATE,
 ADD_EXPENSE, ADD_PRODUCT, EDIT_PRODUCT, DELETE_PRODUCT,
 ADD_STOCK, CHECK_STOCK, SEARCH_ADDRESS, EDIT_ADDRESS_SELECT,
 DELETE_ADDRESS_SELECT, EDIT_ADDRESS_DATA, EDIT_PRODUCT_SELECT,
 DELETE_PRODUCT_SELECT, EDIT_PRODUCT_DATA, ADD_PRODUCT_DATA,
 VIEW_ORDERS_TODAY, VIEW_ORDERS_TOMORROW, MARK_ORDER_DONE,
 CASH_HANDOVER, ENTER_CASH_AMOUNT, STOCK_ARRIVAL, STOCK_WRITEOFF,
 STOCK_WRITEOFF_REASON, SET_MIN_STOCK, ENTER_COMMENT, EDIT_ORDER_SELECT,
 EDIT_ORDER_FIELD) = range(35)

# Роли пользователей
ROLE_DEVELOPER = 'developer'
ROLE_OWNER = 'owner'
ROLE_MANAGER = 'manager'


class CoffeeBot:
    def __init__(self):
        self.users = self.load_users()
        self.gc = None
        self.sheet = None
        self.init_google_sheets()

    def load_users(self):
        """Загрузка пользователей из переменной окружения"""
        users_json = os.getenv('BOT_USERS', '{}')
        try:
            return json.loads(users_json)
        except:
            return {}

    def init_google_sheets(self):
        """Инициализация Google Sheets"""
        try:
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            if not creds_json:
                logger.error("GOOGLE_CREDENTIALS не установлена")
                return

            creds_dict = json.loads(creds_json)
            scope = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]

            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            self.gc = gspread.authorize(creds)

            sheet_id = os.getenv('GOOGLE_SHEET_ID')
            self.sheet = self.gc.open_by_key(sheet_id)

            self.ensure_sheets_exist()

        except Exception as e:
            logger.error(f"Ошибка инициализации Google Sheets: {e}")

    def ensure_sheets_exist(self):
        """Создание необходимых листов в таблице"""
        required_sheets = {
            'Адреса': ['ID', 'Название', 'Адрес', 'Контакт'],
            'Товары': ['ID', 'Название', 'Вес', 'Цена розница', 'Цена опт', 'Цена VIP'],
            'Заказы': ['ID', 'Дата создания', 'Дата доставки', 'Точка', 'Товар', 'Количество', 'Тип цены', 'Сумма',
                       'Статус', 'Дата выполнения', 'Менеджер', 'Комментарий'],
            'Расходы': ['ID', 'Дата', 'Менеджер', 'Описание', 'Сумма'],
            'Остатки': ['Товар', 'Количество', 'Мин. остаток'],
            'Касса менеджеров': ['Менеджер ID', 'Имя менеджера', 'Касса на руках', 'Последнее обновление'],
            'Сдача кассы': ['ID', 'Дата', 'Менеджер', 'Сумма', 'Остаток после сдачи']
        }

        try:
            existing_sheets = [ws.title for ws in self.sheet.worksheets()]

            for sheet_name, headers in required_sheets.items():
                if sheet_name not in existing_sheets:
                    worksheet = self.sheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
                    worksheet.append_row(headers)
                    logger.info(f"Создан лист: {sheet_name}")
                else:
                    # Проверяем существующий лист
                    worksheet = self.sheet.worksheet(sheet_name)
                    all_values = worksheet.get_all_values()

                    # Если лист пустой или нет заголовков, добавляем их
                    if not all_values:
                        worksheet.append_row(headers)
                        logger.info(f"Добавлены заголовки для листа: {sheet_name}")
                    else:
                        # Проверяем и обновляем заголовки
                        existing_headers = all_values[0] if all_values else []

                        # Если заголовки не совпадают или содержат пустые ячейки
                        if existing_headers != headers or '' in existing_headers:
                            logger.warning(f"Обновление заголовков для листа: {sheet_name}")
                            logger.info(f"Было: {existing_headers}")
                            logger.info(f"Стало: {headers}")

                            # Обновляем первую строку с заголовками
                            range_name = f'A1:{chr(65 + len(headers) - 1)}1'
                            worksheet.update(range_name, [headers])
                            logger.info(f"✅ Заголовки обновлены для листа: {sheet_name}")

        except Exception as e:
            logger.error(f"Ошибка создания листов: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def get_user_role(self, user_id):
        """Получение роли пользователя"""
        return self.users.get(str(user_id))

    def has_permission(self, user_id, required_roles):
        """Проверка прав доступа"""
        role = self.get_user_role(user_id)
        return role in required_roles

    # ========== МЕТОДЫ ДЛЯ АДРЕСОВ ==========

    def get_addresses(self, search_query=None):
        """Получение списка адресов"""
        try:
            ws = self.sheet.worksheet('Адреса')
            all_values = ws.get_all_values()

            if not all_values or len(all_values) < 2:
                return []

            headers = all_values[0]
            addresses = []

            for row in all_values[1:]:
                if not row or not row[0]:
                    continue

                address = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        if header == 'ID':
                            try:
                                address[header] = int(row[i]) if row[i] else 0
                            except:
                                address[header] = 0
                        else:
                            address[header] = row[i]
                    else:
                        address[header] = ''

                addresses.append(address)

            if search_query:
                search_query = search_query.lower()
                addresses = [a for a in addresses if
                             search_query in str(a.get('Название', '')).lower() or
                             search_query in str(a.get('Адрес', '')).lower()]

            return addresses
        except Exception as e:
            logger.error(f"Ошибка получения адресов: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def get_address_by_name(self, point_name):
        """Получение адреса точки по её названию"""
        try:
            addresses = self.get_addresses()
            for address in addresses:
                if address.get('Название') == point_name:
                    return address.get('Адрес', '')
            return ''
        except Exception as e:
            logger.error(f"Ошибка получения адреса: {e}")
            return ''

    def add_address(self, name, address, contact=''):
        """Добавление нового адреса"""
        try:
            ws = self.sheet.worksheet('Адреса')

            # Получаем все значения
            all_values = ws.get_all_values()

            # Если таблица пустая, создаем заголовки
            if not all_values:
                headers = ['ID', 'Название', 'Адрес', 'Контакт']
                ws.append_row(headers)
                new_id = 1
            else:
                new_id = len(all_values)

            ws.append_row([new_id, name, address, contact])
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления адреса: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def update_address(self, address_id, name, address, contact=''):
        """Обновление адреса"""
        try:
            ws = self.sheet.worksheet('Адреса')
            cell = ws.find(str(address_id))

            if cell:
                row = cell.row
                ws.update_cell(row, 2, name)  # Название
                ws.update_cell(row, 3, address)  # Адрес
                ws.update_cell(row, 4, contact)  # Контакт
                logger.info(f"Адрес ID {address_id} обновлен")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления адреса: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def delete_address(self, address_id):
        """Удаление адреса"""
        try:
            ws = self.sheet.worksheet('Адреса')
            all_values = ws.get_all_values()

            # Ищем строку с нужным ID
            for i, row in enumerate(all_values):
                if i == 0:  # Пропускаем заголовок
                    continue
                if str(row[0]) == str(address_id):
                    row_number = i + 1
                    ws.delete_rows(row_number)
                    logger.info(f"Адрес ID {address_id} успешно удален")
                    return True

            logger.error(f"Адрес с ID {address_id} не найден")
            return False
        except Exception as e:
            logger.error(f"Ошибка удаления адреса: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def update_address(self, address_id, name, address, contact=''):
        """Редактирование адреса"""
        try:
            ws = self.sheet.worksheet('Адреса')
            all_values = ws.get_all_values()

            # Ищем строку с нужным ID
            for i, row in enumerate(all_values):
                if i == 0:  # Пропускаем заголовок
                    continue
                if str(row[0]) == str(address_id):
                    row_number = i + 1
                    # Обновляем данные адреса (колонки B, C и D)
                    ws.update(f'B{row_number}:D{row_number}', [[name, address, contact]])
                    logger.info(f"Адрес ID {address_id} успешно обновлен")
                    return True

            logger.error(f"Адрес с ID {address_id} не найден")
            return False
        except Exception as e:
            logger.error(f"Ошибка редактирования адреса: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    # ========== МЕТОДЫ ДЛЯ ТОВАРОВ ==========

    def get_products(self):
        """Получение списка товаров"""
        try:
            ws = self.sheet.worksheet('Товары')
            all_values = ws.get_all_values()

            if not all_values or len(all_values) < 2:
                return []

            # Первая строка - заголовки
            headers = all_values[0]

            # Формируем список словарей вручную
            products = []
            for row in all_values[1:]:
                if not row or not row[0]:  # Пропускаем пустые строки
                    continue

                product = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        # Конвертируем числовые значения
                        if header in ['ID']:
                            try:
                                product[header] = int(row[i]) if row[i] else 0
                            except:
                                product[header] = 0
                        elif header in ['Цена розница', 'Цена опт', 'Цена VIP']:
                            try:
                                product[header] = float(row[i]) if row[i] else 0
                            except:
                                product[header] = 0
                        else:
                            product[header] = row[i]
                    else:
                        product[header] = ''

                products.append(product)

            return products
        except Exception as e:
            logger.error(f"Ошибка получения товаров: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def add_product(self, name, weight, price_retail, price_wholesale, price_vip):
        """Добавление нового товара"""
        try:
            ws = self.sheet.worksheet('Товары')

            # Получаем все значения
            all_values = ws.get_all_values()

            # Если таблица пустая, создаем заголовки
            if not all_values:
                headers = ['ID', 'Название', 'Вес', 'Цена розница', 'Цена опт', 'Цена VIP']
                ws.append_row(headers)
                new_id = 1
            else:
                new_id = len(all_values)

            ws.append_row([new_id, name, weight, float(price_retail), float(price_wholesale), float(price_vip)])
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления товара: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def update_product(self, product_id, name, weight, price_retail, price_wholesale, price_vip):
        """Редактирование товара"""
        try:
            ws = self.sheet.worksheet('Товары')
            all_values = ws.get_all_values()

            # Ищем строку с нужным ID (ID находится в первой колонке)
            for i, row in enumerate(all_values):
                if i == 0:  # Пропускаем заголовок
                    continue
                if str(row[0]) == str(product_id):
                    row_number = i + 1
                    # Обновляем данные товара
                    ws.update(f'B{row_number}:F{row_number}',
                              [[name, weight, float(price_retail), float(price_wholesale), float(price_vip)]])
                    logger.info(f"Товар ID {product_id} успешно обновлен")
                    return True

            logger.error(f"Товар с ID {product_id} не найден")
            return False
        except Exception as e:
            logger.error(f"Ошибка редактирования товара: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def delete_product(self, product_id):
        """Удаление товара"""
        try:
            ws = self.sheet.worksheet('Товары')
            all_values = ws.get_all_values()

            # Ищем строку с нужным ID
            for i, row in enumerate(all_values):
                if i == 0:  # Пропускаем заголовок
                    continue
                if str(row[0]) == str(product_id):
                    row_number = i + 1
                    ws.delete_rows(row_number)
                    logger.info(f"Товар ID {product_id} успешно удален")
                    return True

            logger.error(f"Товар с ID {product_id} не найден")
            return False
        except Exception as e:
            logger.error(f"Ошибка удаления товара: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    # ========== МЕТОДЫ ДЛЯ ЗАКАЗОВ ==========

    def add_order(self, delivery_date, point_name, product_name, quantity, price_type, total, comment='',
                  manager_id=None):
        """Добавление нового заказа"""
        try:
            logger.info(
                f"Попытка добавить заказ: дата={delivery_date}, точка={point_name}, товар={product_name}, кол-во={quantity}, тип цены={price_type}, сумма={total}, комментарий={comment}")

            ws = self.sheet.worksheet('Заказы')

            # Получаем все значения из таблицы
            all_values = ws.get_all_values()

            # Если таблица пустая, добавляем заголовки
            if not all_values:
                headers = ['ID', 'Дата создания', 'Дата доставки', 'Точка', 'Товар', 'Количество', 'Тип цены', 'Сумма',
                           'Статус', 'Дата выполнения', 'Менеджер', 'Комментарий']
                ws.append_row(headers)
                new_id = 1
                logger.info("Таблица была пуста, добавлены заголовки")
            else:
                # Количество заказов = количество строк минус заголовок
                new_id = len(all_values)  # Это будет номер новой строки (заголовок + предыдущие заказы)

            created_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            logger.info(f"Новый ID заказа: {new_id}")

            # Данные для записи
            row_data = [
                new_id,
                created_date,
                delivery_date,
                point_name,
                product_name,
                int(quantity),
                price_type,
                float(total),
                'Ожидает',
                '',
                manager_id or '',
                comment
            ]

            logger.info(f"Данные для записи: {row_data}")

            # Добавляем строку
            ws.append_row(row_data)

            logger.info(f"✅ Заказ #{new_id} успешно добавлен в таблицу")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления заказа: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def update_order(self, order_id, delivery_date=None, quantity=None, comment=None):
        """Редактирование заказа"""
        try:
            ws = self.sheet.worksheet('Заказы')
            all_values = ws.get_all_values()

            if not all_values or len(all_values) < 2:
                return False

            headers = all_values[0]

            # Находим строку с нужным ID заказа
            for i, row in enumerate(all_values):
                if i == 0:  # Пропускаем заголовок
                    continue
                if str(row[0]) == str(order_id):
                    row_number = i + 1

                    # Обновляем только переданные поля
                    if delivery_date is not None:
                        # Находим индекс колонки "Дата доставки"
                        try:
                            col_idx = headers.index('Дата доставки')
                            col_letter = chr(65 + col_idx)
                            ws.update(f'{col_letter}{row_number}', [[delivery_date]])
                            logger.info(f"Обновлена дата доставки для заказа #{order_id}: {delivery_date}")
                        except ValueError:
                            logger.error("Колонка 'Дата доставки' не найдена")

                    if quantity is not None:
                        try:
                            qty_idx = headers.index('Количество')
                            sum_idx = headers.index('Сумма')

                            # Получаем текущие значения для пересчета
                            current_qty = float(row[qty_idx]) if row[qty_idx] else 1
                            current_sum = float(row[sum_idx]) if row[sum_idx] else 0
                            price_per_unit = current_sum / current_qty if current_qty > 0 else 0
                            new_sum = quantity * price_per_unit

                            # Обновляем количество
                            col_letter = chr(65 + qty_idx)
                            ws.update(f'{col_letter}{row_number}', [[int(quantity)]])

                            # Обновляем сумму
                            col_letter = chr(65 + sum_idx)
                            ws.update(f'{col_letter}{row_number}', [[float(new_sum)]])

                            logger.info(
                                f"Обновлено количество для заказа #{order_id}: {quantity}, новая сумма: {new_sum}")
                        except ValueError as e:
                            logger.error(f"Ошибка при обновлении количества: {e}")

                    if comment is not None:
                        try:
                            comment_idx = headers.index('Комментарий')
                            col_letter = chr(65 + comment_idx)
                            ws.update(f'{col_letter}{row_number}', [[comment]])
                            logger.info(f"Обновлен комментарий для заказа #{order_id}")
                        except ValueError:
                            logger.error("Колонка 'Комментарий' не найдена")

                    return True

            logger.error(f"Заказ с ID {order_id} не найден")
            return False

        except Exception as e:
            logger.error(f"Ошибка редактирования заказа: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def get_orders_by_date(self, date_str, status=None):
        """Получение заказов по дате доставки"""
        try:
            ws = self.sheet.worksheet('Заказы')

            # Получаем все значения
            all_values = ws.get_all_values()

            # Если таблица пустая или только заголовки
            if len(all_values) <= 1:
                logger.info(f"Таблица Заказы пуста или содержит только заголовки")
                return []

            # Преобразуем в словари (первая строка - заголовки)
            headers = all_values[0]
            logger.info(f"Заголовки таблицы Заказы: {headers}")

            records = []
            for row_idx, row in enumerate(all_values[1:], start=2):
                record = {}
                for i, header in enumerate(headers):
                    record[header] = row[i] if i < len(row) else ''
                records.append(record)
                logger.info(f"Строка {row_idx}: {record}")

            # Отладка
            logger.info(f"Ищем заказы на дату: {date_str}")
            logger.info(f"Всего записей в таблице: {len(records)}")

            # Фильтруем по дате (с проверкой на пустые значения)
            filtered = []
            for r in records:
                delivery_date = str(r.get('Дата доставки', '')).strip()
                logger.info(
                    f"Заказ ID={r.get('ID')}, Дата доставки='{delivery_date}', Сравнение с '{date_str}': {delivery_date == date_str}")

                # Проверяем совпадение даты (игнорируем пустые)
                if delivery_date and delivery_date == date_str:
                    # Нормализуем ключи (используем реальные названия из Google Sheets)
                    # Поддерживаем как новую структуру (с Тип цены), так и старую (без него)
                    normalized = {
                        'ID': r.get('ID', ''),
                        'Дата создания': r.get('Дата создания', ''),
                        'Дата доставки': r.get('Дата доставки', ''),
                        'Точка': r.get('Точка', ''),
                        'Товар': r.get('Товар', ''),
                        'Количество': r.get('Количество', ''),
                        'Тип цены': r.get('Тип цены', 'Розница'),  # Значение по умолчанию для старых заказов
                        'Сумма': r.get('Сумма', ''),
                        'Статус': r.get('Статус', ''),
                        'Дата выполнения': r.get('Дата выполнения', ''),
                        'Менеджер': r.get('Менеджер', '')
                    }
                    filtered.append(normalized)
                    logger.info(f"✅ Заказ {r.get('ID')} добавлен в результаты")

            logger.info(f"Найдено заказов на {date_str}: {len(filtered)}")

            if status:
                filtered = [r for r in filtered if r.get('Статус', '') == status]
                logger.info(f"После фильтра по статусу '{status}': {len(filtered)}")

            # Сортировка по ID
            filtered.sort(key=lambda x: int(x.get('ID', 0)) if x.get('ID') else 0)

            return filtered
        except Exception as e:
            logger.error(f"Ошибка получения заказов: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def mark_order_done(self, order_id, manager_id, manager_name):
        """Отметить заказ как выполненный"""
        try:
            ws = self.sheet.worksheet('Заказы')
            cell = ws.find(str(order_id))

            if cell:
                row = cell.row
                done_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                # Получаем данные заказа ДО обновления статуса
                # Колонки: ID(1), Дата создания(2), Дата доставки(3), Точка(4),
                #          Товар(5), Количество(6), Тип цены(7), Сумма(8),
                #          Статус(9), Дата выполнения(10), Менеджер(11)
                order_sum = float(ws.cell(row, 8).value)  # Сумма в колонке 8
                product_name = ws.cell(row, 5).value  # Товар
                quantity_str = ws.cell(row, 6).value  # Количество

                # Безопасное преобразование количества
                try:
                    quantity = float(quantity_str) if quantity_str else 0
                except (ValueError, TypeError):
                    quantity = 0

                # Обновляем статус и дату выполнения
                ws.update_cell(row, 9, 'Выполнен')  # Статус в колонке 9
                ws.update_cell(row, 10, done_date)  # Дата выполнения в колонке 10
                ws.update_cell(row, 11, f"{manager_name} ({manager_id})")  # Менеджер в колонке 11

                # Обновляем кассу менеджера
                self.update_manager_cash(manager_id, manager_name, order_sum)

                # Списываем остатки со склада (только если это товар, а не услуга)
                if product_name and quantity > 0:
                    self.update_stock(product_name, -quantity)
                    logger.info(f"Списано со склада: {product_name} - {quantity} кг")

                return True, order_sum
            return False, 0
        except Exception as e:
            logger.error(f"Ошибка отметки заказа: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, 0

    # ========== МЕТОДЫ ДЛЯ КАССЫ МЕНЕДЖЕРА ==========

    def get_manager_cash(self, manager_id):
        """Получение суммы кассы менеджера"""
        try:
            ws = self.sheet.worksheet('Касса менеджеров')
            all_values = ws.get_all_values()

            # Если таблица пустая или только с заголовками
            if len(all_values) <= 1:
                return 0.0

            # Ищем менеджера (пропускаем заголовок)
            for row in all_values[1:]:
                if len(row) > 2 and str(row[0]) == str(manager_id):
                    return float(row[2] if row[2] else 0)

            return 0.0
        except Exception as e:
            logger.error(f"Ошибка получения кассы: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0.0

    def update_manager_cash(self, manager_id, manager_name, amount):
        """Обновление кассы менеджера"""
        try:
            ws = self.sheet.worksheet('Касса менеджеров')

            # Получаем все значения
            all_values = ws.get_all_values()

            # Если таблица пустая, создаем заголовки
            if not all_values:
                headers = ['Менеджер ID', 'Имя менеджера', 'Касса на руках', 'Последнее обновление']
                ws.append_row(headers)
                all_values = [headers]
                logger.info("Создана таблица Касса менеджеров с заголовками")

            # Ищем менеджера в таблице
            manager_row = None
            for idx, row in enumerate(all_values[1:], start=2):  # Начинаем со второй строки (пропускаем заголовок)
                if len(row) > 0 and str(row[0]) == str(manager_id):
                    manager_row = idx
                    break

            if manager_row:
                # Менеджер найден - обновляем сумму
                current_cash = float(ws.cell(manager_row, 3).value or 0)
                new_cash = current_cash + amount
                ws.update_cell(manager_row, 3, new_cash)
                ws.update_cell(manager_row, 4, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                logger.info(f"Касса менеджера {manager_id} обновлена: {current_cash} + {amount} = {new_cash}")
            else:
                # Новый менеджер - добавляем запись
                ws.append_row([
                    manager_id,
                    manager_name,
                    amount,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ])
                logger.info(f"Добавлен новый менеджер {manager_id} с кассой {amount}")

            return True
        except Exception as e:
            logger.error(f"Ошибка обновления кассы: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    # ========== МЕТОДЫ ДЛЯ РАСХОДОВ ==========

    def add_expense(self, manager_id, manager_name, description, amount):
        """Добавление расхода"""
        try:
            ws = self.sheet.worksheet('Расходы')

            # Получаем все значения
            all_values = ws.get_all_values()

            # Если таблица пустая, создаем заголовки
            if not all_values:
                headers = ['№', 'Дата', 'Менеджер', 'Описание', 'Сумма']
                ws.append_row(headers)
                new_id = 1
            else:
                new_id = len(all_values)  # количество строк = ID следующей записи

            date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            ws.append_row([new_id, date, f"{manager_name} ({manager_id})", description, float(amount)])

            # Вычитаем из кассы менеджера
            self.update_manager_cash(manager_id, manager_name, -float(amount))

            return True
        except Exception as e:
            logger.error(f"Ошибка добавления расхода: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    # ========== МЕТОДЫ ДЛЯ СДАЧИ КАССЫ ==========

    def handover_cash(self, manager_id, manager_name, amount):
        """Сдача кассы"""
        try:
            # Получаем текущую кассу
            current_cash = self.get_manager_cash(manager_id)

            if current_cash < amount:
                return False, "Недостаточно средств в кассе"

            # Вычитаем сданную сумму
            self.update_manager_cash(manager_id, manager_name, -amount)

            # Записываем в историю сдачи
            ws = self.sheet.worksheet('Сдача кассы')

            # Получаем все значения
            all_values = ws.get_all_values()

            # Если таблица пустая, создаем заголовки
            if not all_values:
                headers = ['№', 'Дата', 'Менеджер', 'Сдано', 'Остаток']
                ws.append_row(headers)
                new_id = 1
            else:
                new_id = len(all_values)  # количество строк = ID следующей записи

            remaining_cash = current_cash - amount

            ws.append_row([
                new_id,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                f"{manager_name} ({manager_id})",
                amount,
                remaining_cash
            ])

            return True, remaining_cash
        except Exception as e:
            logger.error(f"Ошибка сдачи кассы: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)

    # ========== МЕТОДЫ ДЛЯ ОСТАТКОВ ==========

    def get_stock(self):
        """Получение текущих остатков"""
        try:
            ws = self.sheet.worksheet('Остатки')
            all_values = ws.get_all_values()

            if len(all_values) <= 1:
                return []

            # Преобразуем в словари
            headers = all_values[0]
            stock = []
            for row in all_values[1:]:
                if len(row) >= 3 and row[0]:  # Проверяем что есть название товара
                    stock.append({
                        'Товар': row[0],
                        'Количество': float(row[1]) if row[1] else 0,
                        'Мин. остаток': float(row[2]) if row[2] else 0
                    })
            return stock
        except Exception as e:
            logger.error(f"Ошибка получения остатков: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def update_stock(self, product_name, quantity, min_stock=None):
        """Обновление остатка товара"""
        try:
            ws = self.sheet.worksheet('Остатки')
            all_values = ws.get_all_values()

            # Если таблица пустая, создаем заголовки
            if not all_values:
                headers = ['Товар', 'Количество', 'Мин. остаток']
                ws.append_row(headers)
                all_values = [headers]

            # Ищем товар
            product_row = None
            for idx, row in enumerate(all_values[1:], start=2):
                if len(row) > 0 and row[0] == product_name:
                    product_row = idx
                    break

            if product_row:
                # Товар найден - обновляем количество
                current_qty = float(ws.cell(product_row, 2).value or 0)
                new_qty = current_qty + quantity
                ws.update_cell(product_row, 2, new_qty)

                if min_stock is not None:
                    ws.update_cell(product_row, 3, min_stock)

                logger.info(f"Остаток {product_name} обновлен: {current_qty} + {quantity} = {new_qty}")
            else:
                # Новый товар - добавляем запись
                ws.append_row([
                    product_name,
                    quantity,
                    min_stock if min_stock is not None else 0
                ])
                logger.info(f"Добавлен новый товар в остатки: {product_name}, количество: {quantity}")

            return True
        except Exception as e:
            logger.error(f"Ошибка обновления остатков: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def set_stock(self, product_name, quantity, min_stock=None):
        """Установка точного остатка товара (не добавление, а замена)"""
        try:
            ws = self.sheet.worksheet('Остатки')
            all_values = ws.get_all_values()

            # Если таблица пустая, создаем заголовки
            if not all_values:
                headers = ['Товар', 'Количество', 'Мин. остаток']
                ws.append_row(headers)
                all_values = [headers]

            # Ищем товар
            product_row = None
            for idx, row in enumerate(all_values[1:], start=2):
                if len(row) > 0 and row[0] == product_name:
                    product_row = idx
                    break

            if product_row:
                # Товар найден - устанавливаем новое количество
                ws.update_cell(product_row, 2, quantity)

                if min_stock is not None:
                    ws.update_cell(product_row, 3, min_stock)

                logger.info(f"Остаток {product_name} установлен: {quantity}")
            else:
                # Новый товар - добавляем запись
                ws.append_row([
                    product_name,
                    quantity,
                    min_stock if min_stock is not None else 0
                ])
                logger.info(f"Добавлен новый товар в остатки: {product_name}, количество: {quantity}")

            return True
        except Exception as e:
            logger.error(f"Ошибка установки остатков: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    # ========== МЕТОДЫ ДЛЯ СТАТИСТИКИ ==========

    def get_daily_total(self):
        """Получение итога за день (только выполненные заказы)"""
        try:
            ws = self.sheet.worksheet('Заказы')
            all_values = ws.get_all_values()

            if not all_values or len(all_values) < 2:
                return 0

            headers = all_values[0]
            today = datetime.now().strftime('%Y-%m-%d')

            # Находим индексы нужных колонок
            try:
                sum_idx = headers.index('Сумма')
                date_done_idx = headers.index('Дата выполнения')
            except ValueError:
                logger.error("Не найдены необходимые колонки в таблице Заказы")
                return 0

            total = 0
            for row in all_values[1:]:
                if len(row) > max(sum_idx, date_done_idx):
                    date_done = row[date_done_idx] if date_done_idx < len(row) else ''
                    if date_done and date_done.startswith(today):
                        try:
                            total += float(row[sum_idx])
                        except (ValueError, IndexError):
                            pass

            return total
        except Exception as e:
            logger.error(f"Ошибка расчета дневного итога: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0

    def get_monthly_total(self):
        """Получение итога за месяц (только выполненные заказы)"""
        try:
            ws = self.sheet.worksheet('Заказы')
            all_values = ws.get_all_values()

            if not all_values or len(all_values) < 2:
                return 0

            headers = all_values[0]
            current_month = datetime.now().strftime('%Y-%m')

            try:
                sum_idx = headers.index('Сумма')
                date_done_idx = headers.index('Дата выполнения')
            except ValueError:
                logger.error("Не найдены необходимые колонки в таблице Заказы")
                return 0

            total = 0
            for row in all_values[1:]:
                if len(row) > max(sum_idx, date_done_idx):
                    date_done = row[date_done_idx] if date_done_idx < len(row) else ''
                    if date_done and date_done.startswith(current_month):
                        try:
                            total += float(row[sum_idx])
                        except (ValueError, IndexError):
                            pass

            return total
        except Exception as e:
            logger.error(f"Ошибка расчета месячного итога: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0

    def get_monthly_expenses(self):
        """Получение расходов за месяц"""
        try:
            ws = self.sheet.worksheet('Расходы')
            all_values = ws.get_all_values()

            if not all_values or len(all_values) < 2:
                return 0

            headers = all_values[0]
            current_month = datetime.now().strftime('%Y-%m')

            try:
                sum_idx = headers.index('Сумма')
                date_idx = headers.index('Дата')
            except ValueError:
                logger.error("Не найдены необходимые колонки в таблице Расходы")
                return 0

            total = 0
            for row in all_values[1:]:
                if len(row) > max(sum_idx, date_idx):
                    date = row[date_idx] if date_idx < len(row) else ''
                    if date and date.startswith(current_month):
                        try:
                            total += float(row[sum_idx])
                        except (ValueError, IndexError):
                            pass

            return total
        except Exception as e:
            logger.error(f"Ошибка расчета расходов: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0


# Глобальный объект бота будет инициализирован после определения всех функций


# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    role = bot_instance.get_user_role(user_id)

    if not role:
        await update.message.reply_text(
            "❌ У вас нет доступа к боту.\n"
            "Обратитесь к администратору для получения доступа."
        )
        return ConversationHandler.END

    role_names = {
        ROLE_DEVELOPER: "Разработчик",
        ROLE_OWNER: "Владелец",
        ROLE_MANAGER: "Менеджер"
    }

    keyboard = []

    # Общие команды для всех
    keyboard.append([KeyboardButton("📦 Новый заказ")])

    # Команды для менеджера и выше
    if role in [ROLE_MANAGER, ROLE_OWNER, ROLE_DEVELOPER]:
        keyboard.append([KeyboardButton("📋 Заказы на сегодня"), KeyboardButton("📅 Заказы на завтра")])
        keyboard.append([KeyboardButton("💰 Добавить расход"), KeyboardButton("💵 Сдать кассу")])
        keyboard.append([KeyboardButton("💼 Моя касса")])

    # Команды только для владельца и разработчика
    if role in [ROLE_OWNER, ROLE_DEVELOPER]:
        keyboard.append([KeyboardButton("📍 Управление адресами"), KeyboardButton("☕ Управление товарами")])
        keyboard.append([KeyboardButton("📦 Управление остатками")])
        keyboard.append([KeyboardButton("📊 Статистика")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Показываем кассу для менеджеров
    cash_info = ""
    if role in [ROLE_MANAGER, ROLE_OWNER, ROLE_DEVELOPER]:
        cash = bot_instance.get_manager_cash(user_id)
        cash_info = f"\n💵 Ваша касса: {cash:,.2f} грн"

    await update.message.reply_text(
        f"👋 Добро пожаловать в систему учета заказов кофе!\n"
        f"Ваша роль: {role_names.get(role, 'Неизвестна')}{cash_info}\n\n"
        f"Выберите действие из меню:",
        reply_markup=reply_markup
    )

    return CHOOSING_ACTION


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик меню"""
    user_id = update.effective_user.id
    role = bot_instance.get_user_role(user_id)
    text = update.message.text

    if text == "📦 Новый заказ":
        return await start_new_order(update, context)

    elif text == "📊 Статистика":
        return await show_statistics(update, context)

    elif text == "📋 Заказы на сегодня":
        if role in [ROLE_MANAGER, ROLE_OWNER, ROLE_DEVELOPER]:
            return await show_orders_today(update, context)

    elif text == "📅 Заказы на завтра":
        if role in [ROLE_MANAGER, ROLE_OWNER, ROLE_DEVELOPER]:
            return await show_orders_tomorrow(update, context)

    elif text == "💼 Моя касса":
        if role in [ROLE_MANAGER, ROLE_OWNER, ROLE_DEVELOPER]:
            return await show_my_cash(update, context)

    elif text == "💰 Добавить расход":
        if role in [ROLE_MANAGER, ROLE_OWNER, ROLE_DEVELOPER]:
            await update.message.reply_text(
                "Введите описание расхода и сумму через запятую:\n"
                "Например: Транспорт, 500"
            )
            return ADD_EXPENSE

    elif text == "💵 Сдать кассу":
        if role in [ROLE_MANAGER, ROLE_OWNER, ROLE_DEVELOPER]:
            cash = bot_instance.get_manager_cash(user_id)
            await update.message.reply_text(
                f"💵 Ваша текущая касса: {cash:,.2f} грн\n\n"
                f"Введите сумму для сдачи:"
            )
            return CASH_HANDOVER

    elif text == "📍 Управление адресами":
        if role in [ROLE_OWNER, ROLE_DEVELOPER]:
            return await manage_addresses(update, context)

    elif text == "☕ Управление товарами":
        if role in [ROLE_OWNER, ROLE_DEVELOPER]:
            return await manage_products(update, context)

    elif text == "📦 Управление остатками":
        if role in [ROLE_OWNER, ROLE_DEVELOPER]:
            return await manage_stock(update, context)

    return CHOOSING_ACTION


# ========== СОЗДАНИЕ ЗАКАЗА ==========

async def start_new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало оформления нового заказа"""
    addresses = bot_instance.get_addresses()

    if not addresses:
        await update.message.reply_text("❌ Нет доступных адресов. Добавьте адреса в систему.")
        return CHOOSING_ACTION

    keyboard = []
    for addr in addresses[:10]:
        keyboard.append([InlineKeyboardButton(
            f"{addr['Название']} - {addr['Адрес']}",
            callback_data=f"addr_{addr['ID']}"
        )])

    keyboard.append([InlineKeyboardButton("🔍 Поиск адреса", callback_data="search_address")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите торговую точку:", reply_markup=reply_markup)

    return SELECT_ADDRESS


async def handle_address_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора адреса"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("Операция отменена. Используйте /start для возврата в меню.")
        return ConversationHandler.END

    if query.data.startswith("addr_"):
        addr_id = int(query.data.split("_")[1])
        addresses = bot_instance.get_addresses()
        selected_address = next((a for a in addresses if a['ID'] == addr_id), None)

        if selected_address:
            context.user_data['selected_address'] = selected_address

            # Показываем товары
            products = bot_instance.get_products()
            if not products:
                await query.edit_message_text("❌ Нет доступных товаров.")
                return CHOOSING_ACTION

            # Получаем остатки
            stock = bot_instance.get_stock()

            keyboard = []
            for prod in products:
                # Проверяем есть ли товар на складе
                stock_item = next((s for s in stock if s['Товар'] == prod['Название']), None)
                stock_qty = stock_item['Количество'] if stock_item else 0

                # Показываем только товары с остатком > 0
                if stock_qty > 0:
                    keyboard.append([InlineKeyboardButton(
                        f"{prod['Название']} {prod['Вес']} - от {prod.get('Цена розница', 0)} грн (на складе: {stock_qty:.1f} кг)",
                        callback_data=f"prod_{prod['ID']}"
                    )])

            if not keyboard:
                await query.edit_message_text(
                    "❌ К сожалению, все товары закончились на складе.\n"
                    "Пожалуйста, добавьте поступление товаров."
                )
                return CHOOSING_ACTION

            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Торговая точка: {selected_address['Название']}\n\n"
                f"Выберите товар:",
                reply_markup=reply_markup
            )

            return SELECT_PRODUCT

    elif query.data == "search_address":
        await query.edit_message_text("Введите название или адрес для поиска:")
        return SEARCH_ADDRESS

    return SELECT_ADDRESS


async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора товара"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("Операция отменена. Используйте /start для возврата в меню.")
        return ConversationHandler.END

    if query.data.startswith("prod_"):
        prod_id = int(query.data.split("_")[1])
        products = bot_instance.get_products()
        selected_product = next((p for p in products if p['ID'] == prod_id), None)

        if selected_product:
            context.user_data['selected_product'] = selected_product

            # Получаем цены из новых колонок
            price_retail = selected_product.get('Цена розница', 0)
            price_wholesale = selected_product.get('Цена опт', 0)
            price_vip = selected_product.get('Цена VIP', 0)

            # Показываем кнопки для выбора типа цены
            keyboard = [
                [InlineKeyboardButton(f"🛍️ Розница - {price_retail} грн",
                                      callback_data="price_retail")],
                [InlineKeyboardButton(f"📦 Опт - {price_wholesale} грн",
                                      callback_data="price_wholesale")],
                [InlineKeyboardButton(f"⭐ VIP - {price_vip} грн", callback_data="price_vip")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"Товар: {selected_product['Название']} {selected_product['Вес']}\n\n"
                f"Выберите тип цены:",
                reply_markup=reply_markup
            )

            return SELECT_PRODUCT

    # Обработка выбора типа цены
    if query.data.startswith("price_"):
        price_type = query.data.split("_")[1]
        product = context.user_data.get('selected_product')

        if product:
            # Определяем цену в зависимости от типа
            if price_type == "retail":
                price = float(product.get('Цена розница', 0))
                price_label = "Розница"
            elif price_type == "wholesale":
                price = float(product.get('Цена опт', 0))
                price_label = "Опт"
            elif price_type == "vip":
                price = float(product.get('Цена VIP', 0))
                price_label = "VIP"
            else:
                await query.edit_message_text("❌ Ошибка выбора типа цены")
                return SELECT_PRODUCT

            # Проверка что цена не равна 0
            if price == 0:
                logger.error(f"Цена товара равна 0! Товар: {product}")
                await query.edit_message_text(
                    "❌ Ошибка: цена товара не установлена.\n"
                    "Пожалуйста, обновите товар с корректными ценами."
                )
                return CHOOSING_ACTION

            context.user_data['price_type'] = price_label
            context.user_data['selected_price'] = price

            await query.edit_message_text(
                f"Товар: {product['Название']} {product['Вес']}\n"
                f"Тип цены: {price_label}\n"
                f"Цена за упаковку: {price} грн\n\n"
                f"Введите количество упаковок:"
            )

            return ENTER_QUANTITY

    # Обработка кнопки "Добавить еще товар"
    if query.data == "add_more_products":
        # Показываем товары снова
        products = bot_instance.get_products()
        if not products:
            await query.edit_message_text("❌ Нет доступных товаров.")
            return CHOOSING_ACTION

        # Получаем остатки
        stock = bot_instance.get_stock()

        keyboard = []
        for prod in products:
            # Проверяем есть ли товар на складе
            stock_item = next((s for s in stock if s['Товар'] == prod['Название']), None)
            stock_qty = stock_item['Количество'] if stock_item else 0

            # Показываем только товары с остатком > 0
            if stock_qty > 0:
                keyboard.append([InlineKeyboardButton(
                    f"{prod['Название']} {prod['Вес']} - от {prod.get('Цена розница', 0)} грн (на складе: {stock_qty:.1f} кг)",
                    callback_data=f"prod_{prod['ID']}"
                )])

        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите товар:", reply_markup=reply_markup)

        return SELECT_PRODUCT

    # Обработка кнопки "Добавить услугу"
    if query.data == "add_service":
        await query.edit_message_text(
            "🔧 <b>Добавление услуги</b>\n\n"
            "Введите название услуги и стоимость через запятую:\n"
            "Например: Доставка, 100",
            parse_mode='HTML'
        )
        return ENTER_QUANTITY  # Используем это состояние для обработки услуги

    # Обработка кнопки "Продолжить оформление"
    if query.data == "proceed_to_delivery":
        # Спрашиваем дату доставки
        keyboard = [
            [InlineKeyboardButton("📅 Сегодня", callback_data="delivery_today")],
            [InlineKeyboardButton("📅 Завтра", callback_data="delivery_tomorrow")],
            [InlineKeyboardButton("📅 Другая дата", callback_data="delivery_custom")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        cart_total = sum(item['total'] for item in context.user_data.get('cart_items', []))

        await query.edit_message_text(
            f"💰 <b>Итоговая сумма: {cart_total:,.2f} грн</b>\n\n"
            f"Выберите дату доставки:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

        return ENTER_DELIVERY_DATE

    return SELECT_PRODUCT


async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода количества"""
    try:
        text = update.message.text.strip()

        # Проверка на отмену
        if text.lower() in ['/q', 'q', '/cancel', 'cancel']:
            context.user_data.clear()
            await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
            return CHOOSING_ACTION

        # Проверяем, это ввод услуги (содержит запятую) или количество товара
        if ',' in text:
            # Это услуга: Название, Стоимость
            parts = text.split(',')
            if len(parts) != 2:
                await update.message.reply_text(
                    "❌ Неверный формат. Используйте: Название услуги, Стоимость\n"
                    "Например: Доставка, 100"
                )
                return ENTER_QUANTITY

            service_name = parts[0].strip()
            service_cost = float(parts[1].strip())

            if service_cost <= 0:
                await update.message.reply_text("❌ Стоимость должна быть больше нуля.")
                return ENTER_QUANTITY

            # Добавляем услугу в корзину
            if 'cart_items' not in context.user_data:
                context.user_data['cart_items'] = []

            context.user_data['cart_items'].append({
                'product': f"🔧 {service_name}",
                'quantity': 1,
                'price_type': 'Услуга',
                'price': service_cost,
                'total': service_cost
            })

            # Считаем общую сумму корзины
            cart_total = sum(item['total'] for item in context.user_data['cart_items'])

            logger.info(f"Услуга добавлена в корзину: {service_name}, стоимость={service_cost}")

            # Показываем текущую корзину
            cart_text = "🛒 <b>Корзина:</b>\n\n"
            for idx, item in enumerate(context.user_data['cart_items'], 1):
                if item['price_type'] == 'Услуга':
                    cart_text += f"{idx}. {item['product']}\n"
                    cart_text += f"   💰 {item['total']:,.2f} грн\n\n"
                else:
                    cart_text += f"{idx}. {item['product']} × {item['quantity']} кг ({item['price_type']})\n"
                    cart_text += f"   💰 {item['total']:,.2f} грн\n\n"
            cart_text += f"<b>Итого: {cart_total:,.2f} грн</b>"

            await update.message.reply_text(cart_text, parse_mode='HTML')

            # Спрашиваем что делать дальше
            keyboard = [
                [InlineKeyboardButton("➕ Добавить еще товар", callback_data="add_more_products")],
                [InlineKeyboardButton("🔧 Добавить услугу", callback_data="add_service")],
                [InlineKeyboardButton("✅ Продолжить оформление", callback_data="proceed_to_delivery")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Что дальше?",
                reply_markup=reply_markup
            )

            return SELECT_PRODUCT

        # Это количество товара
        quantity = int(text)

        if quantity <= 0:
            await update.message.reply_text(
                "❌ Количество должно быть больше нуля. Попробуйте снова:\n\n"
                "Введите /q для выхода в главное меню."
            )
            return ENTER_QUANTITY

        # Проверяем наличие товара на складе
        product = context.user_data.get('selected_product')
        product_name = product.get('Название')

        stock = bot_instance.get_stock()
        stock_item = next((s for s in stock if s['Товар'] == product_name), None)
        available_qty = stock_item['Количество'] if stock_item else 0

        if quantity > available_qty:
            await update.message.reply_text(
                f"❌ Недостаточно товара на складе!\n\n"
                f"📦 Доступно: {available_qty:.1f} кг\n"
                f"❗ Запрошено: {quantity} кг\n\n"
                f"Введите другое количество или /q для отмены."
            )
            return ENTER_QUANTITY

        selected_price = context.user_data.get('selected_price', 0)
        price_type = context.user_data.get('price_type', 'Розница')

        # Добавляем товар в корзину
        if 'cart_items' not in context.user_data:
            context.user_data['cart_items'] = []

        item_total = quantity * float(selected_price)
        context.user_data['cart_items'].append({
            'product': product['Название'],
            'quantity': quantity,
            'price_type': price_type,
            'price': selected_price,
            'total': item_total
        })

        # Считаем общую сумму корзины
        cart_total = sum(item['total'] for item in context.user_data['cart_items'])

        logger.info(f"Товар добавлен в корзину: {product['Название']}, количество={quantity}, сумма={item_total}")

        # Показываем текущую корзину и спрашиваем что делать дальше
        cart_text = "🛒 <b>Корзина:</b>\n\n"
        for idx, item in enumerate(context.user_data['cart_items'], 1):
            if item.get('price_type') == 'Услуга':
                cart_text += f"{idx}. {item['product']}\n"
                cart_text += f"   💰 {item['total']:,.2f} грн\n\n"
            else:
                cart_text += f"{idx}. {item['product']} × {item['quantity']} кг ({item['price_type']})\n"
                cart_text += f"   💰 {item['total']:,.2f} грн\n\n"
        cart_text += f"<b>Итого: {cart_total:,.2f} грн</b>"

        await update.message.reply_text(cart_text, parse_mode='HTML')

        # Спрашиваем что делать дальше
        keyboard = [
            [InlineKeyboardButton("➕ Добавить еще товар", callback_data="add_more_products")],
            [InlineKeyboardButton("🔧 Добавить услугу", callback_data="add_service")],
            [InlineKeyboardButton("✅ Продолжить оформление", callback_data="proceed_to_delivery")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Что дальше?",
            reply_markup=reply_markup
        )

        return SELECT_PRODUCT

    except ValueError:
        await update.message.reply_text(
            "❌ Введите корректное число:\n\n"
            "Введите /q для выхода в главное меню."
        )
        return ENTER_QUANTITY


async def handle_delivery_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора даты доставки"""
    query = update.callback_query
    await query.answer()

    logger.info(f"Обработка даты доставки, callback_data: {query.data}")

    if query.data == "delivery_today":
        delivery_date = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"Выбрана дата: Сегодня ({delivery_date})")
    elif query.data == "delivery_tomorrow":
        delivery_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        logger.info(f"Выбрана дата: Завтра ({delivery_date})")
    elif query.data == "delivery_custom":
        await query.edit_message_text(
            "Введите дату доставки в формате ДД.ММ.ГГГГ:\n"
            "Например: 20.02.2026"
        )
        return ENTER_DELIVERY_DATE
    else:
        logger.warning(f"Неизвестный callback_data: {query.data}")
        return ENTER_DELIVERY_DATE

    # Сохраняем дату доставки и запрашиваем комментарий
    context.user_data['delivery_date'] = delivery_date

    await query.edit_message_text(
        "💬 <b>Комментарий к заказу</b>\n\n"
        "Введите комментарий (например, контактное лицо и номер телефона)\n"
        "или отправьте '-' если комментарий не нужен:",
        parse_mode='HTML'
    )

    return ENTER_COMMENT


async def handle_custom_delivery_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода пользовательской даты"""
    try:
        date_str = update.message.text
        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
        delivery_date = date_obj.strftime('%Y-%m-%d')

        # Сохраняем дату доставки и запрашиваем комментарий
        context.user_data['delivery_date'] = delivery_date

        await update.message.reply_text(
            "💬 <b>Комментарий к заказу</b>\n\n"
            "Введите комментарий (например, контактное лицо и номер телефона)\n"
            "или отправьте '-' если комментарий не нужен:",
            parse_mode='HTML'
        )

        return ENTER_COMMENT

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ\n"
            "Например: 20.02.2026"
        )
        return ENTER_DELIVERY_DATE


async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода комментария и создание заказов"""
    comment = update.message.text.strip()

    # Если пользователь ввел '-', комментарий не добавляем
    if comment == '-':
        comment = ''

    # Получаем все данные заказа
    delivery_date = context.user_data.get('delivery_date')
    address = context.user_data.get('selected_address')
    cart_items = context.user_data.get('cart_items', [])

    logger.info(f"Создание заказов: дата={delivery_date}, адрес={address}, корзина={cart_items}, комментарий={comment}")

    if not address or not cart_items or not delivery_date:
        await update.message.reply_text("❌ Ошибка: потеряны данные заказа.")
        context.user_data.clear()
        return CHOOSING_ACTION

    # Создаем заказ для каждого товара/услуги в корзине
    created_orders = []
    for item in cart_items:
        product_name = item['product']
        quantity = item['quantity']
        price_type = item['price_type']
        total = item['total']

        if bot_instance.add_order(delivery_date, address['Название'], product_name, quantity, price_type, total,
                                  comment):
            created_orders.append(item)
            logger.info(f"Создан заказ: {product_name}, кол-во={quantity}, сумма={total}")
        else:
            logger.error(f"Ошибка создания заказа: {product_name}")

    if created_orders:
        cart_total = sum(item['total'] for item in created_orders)

        result_text = "✅ <b>Заказы успешно созданы!</b>\n\n"
        result_text += f"📍 Точка: {address['Название']}\n"
        result_text += f"📅 Дата доставки: {delivery_date}\n"
        if comment:
            result_text += f"💬 Комментарий: {comment}\n"
        result_text += "\n<b>Состав заказа:</b>\n"

        for idx, item in enumerate(created_orders, 1):
            if item['price_type'] == 'Услуга':
                result_text += f"{idx}. {item['product']}\n"
                result_text += f"   💰 {item['total']:,.2f} грн\n"
            else:
                result_text += f"{idx}. {item['product']} × {item['quantity']} кг ({item['price_type']})\n"
                result_text += f"   💰 {item['total']:,.2f} грн\n"

        result_text += f"\n<b>💰 Итого: {cart_total:,.2f} грн</b>\n\n"
        result_text += "Используйте /start для возврата в меню."

        await update.message.reply_text(result_text, parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Ошибка при сохранении заказов.")

    context.user_data.clear()
    return CHOOSING_ACTION


async def handle_edit_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка начала редактирования заказа"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("editorder_"):
        order_id = query.data.split("_")[1]
        context.user_data['edit_order_id'] = order_id

        # Получаем информацию о заказе
        today = datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

        orders_today = bot_instance.get_orders_by_date(today)
        orders_tomorrow = bot_instance.get_orders_by_date(tomorrow)
        all_orders = orders_today + orders_tomorrow

        order = next((o for o in all_orders if str(o['ID']) == str(order_id)), None)

        if order:
            context.user_data['edit_order'] = order

            keyboard = [
                [InlineKeyboardButton("📅 Изменить дату доставки", callback_data="edit_field_date")],
                [InlineKeyboardButton("📦 Изменить количество", callback_data="edit_field_quantity")],
                [InlineKeyboardButton("💬 Изменить комментарий", callback_data="edit_field_comment")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"✏️ <b>Редактирование заказа #{order_id}</b>\n\n"
                f"📍 Точка: {order['Точка']}\n"
                f"☕ Товар: {order['Товар']}\n"
                f"📦 Количество: {order['Количество']} кг\n"
                f"📅 Дата доставки: {order['Дата доставки']}\n"
                f"💬 Комментарий: {order.get('Комментарий', '-')}\n\n"
                f"Что вы хотите изменить?",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return EDIT_ORDER_SELECT
        else:
            await query.edit_message_text("❌ Заказ не найден")
            return CHOOSING_ACTION

    return CHOOSING_ACTION


async def handle_edit_field_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора поля для редактирования"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("Операция отменена. Используйте /start для возврата в меню.")
        return CHOOSING_ACTION

    if query.data == "edit_field_date":
        context.user_data['edit_field'] = 'date'
        await query.edit_message_text(
            "📅 <b>Изменение даты доставки</b>\n\n"
            "Введите новую дату в формате ДД.ММ.ГГГГ\n"
            "Например: 25.02.2026",
            parse_mode='HTML'
        )
        return EDIT_ORDER_FIELD

    elif query.data == "edit_field_quantity":
        context.user_data['edit_field'] = 'quantity'
        await query.edit_message_text(
            "📦 <b>Изменение количества</b>\n\n"
            "Введите новое количество в кг:",
            parse_mode='HTML'
        )
        return EDIT_ORDER_FIELD

    elif query.data == "edit_field_comment":
        context.user_data['edit_field'] = 'comment'
        await query.edit_message_text(
            "💬 <b>Изменение комментария</b>\n\n"
            "Введите новый комментарий\n"
            "или '-' чтобы удалить комментарий:",
            parse_mode='HTML'
        )
        return EDIT_ORDER_FIELD

    return EDIT_ORDER_SELECT


async def handle_edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода нового значения поля"""
    text = update.message.text.strip()
    order_id = context.user_data.get('edit_order_id')
    edit_field = context.user_data.get('edit_field')
    order = context.user_data.get('edit_order')

    if not order_id or not edit_field or not order:
        await update.message.reply_text("❌ Ошибка: потеряны данные редактирования")
        context.user_data.clear()
        return CHOOSING_ACTION

    try:
        if edit_field == 'date':
            # Парсим дату
            date_obj = datetime.strptime(text, '%d.%m.%Y')
            new_date = date_obj.strftime('%Y-%m-%d')

            if bot_instance.update_order(order_id, delivery_date=new_date):
                await update.message.reply_text(
                    f"✅ Дата доставки обновлена!\n\n"
                    f"Было: {order['Дата доставки']}\n"
                    f"Стало: {new_date}\n\n"
                    f"Используйте /start для возврата в меню."
                )
            else:
                await update.message.reply_text("❌ Ошибка при обновлении заказа")

        elif edit_field == 'quantity':
            new_quantity = int(text)

            if new_quantity <= 0:
                await update.message.reply_text("❌ Количество должно быть больше нуля")
                return EDIT_ORDER_FIELD

            if bot_instance.update_order(order_id, quantity=new_quantity):
                await update.message.reply_text(
                    f"✅ Количество обновлено!\n\n"
                    f"Было: {order['Количество']} кг\n"
                    f"Стало: {new_quantity} кг\n\n"
                    f"Используйте /start для возврата в меню."
                )
            else:
                await update.message.reply_text("❌ Ошибка при обновлении заказа")

        elif edit_field == 'comment':
            new_comment = '' if text == '-' else text

            if bot_instance.update_order(order_id, comment=new_comment):
                await update.message.reply_text(
                    f"✅ Комментарий обновлен!\n\n"
                    f"Было: {order.get('Комментарий', '-')}\n"
                    f"Стало: {new_comment if new_comment else '-'}\n\n"
                    f"Используйте /start для возврата в меню."
                )
            else:
                await update.message.reply_text("❌ Ошибка при обновлении заказа")

        context.user_data.clear()
        return CHOOSING_ACTION

    except ValueError as e:
        await update.message.reply_text(
            f"❌ Неверный формат данных. Попробуйте снова.\n"
            f"Ошибка: {str(e)}"
        )
        return EDIT_ORDER_FIELD


# ========== ПРОСМОТР ЗАКАЗОВ ==========

async def show_orders_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ заказов на сегодня"""
    today = datetime.now().strftime('%Y-%m-%d')
    orders = bot_instance.get_orders_by_date(today)

    if not orders:
        await update.message.reply_text("📋 На сегодня заказов нет.")
        return CHOOSING_ACTION

    # Сортируем по дате создания (по возрастанию)
    orders.sort(key=lambda x: x.get('Дата создания', ''))

    # Разделяем на выполненные и ожидающие
    pending = [o for o in orders if o['Статус'] == 'Ожидает']
    done = [o for o in orders if o['Статус'] == 'Выполнен']

    # Отправляем заголовок
    await update.message.reply_text(f"📋 <b>Заказы на сегодня ({today})</b>", parse_mode='HTML')

    # Группируем ожидающие заказы по адресу
    if pending:
        await update.message.reply_text("<b>⏳ Ожидают выполнения:</b>", parse_mode='HTML')

        # Группируем по точке (адресу)
        from collections import defaultdict
        grouped = defaultdict(list)
        for order in pending:
            point_name = order['Точка']
            grouped[point_name].append(order)

        # Выводим заказы сгруппированные по адресу
        for point_name in sorted(grouped.keys()):
            point_orders = grouped[point_name]

            # Получаем адрес один раз для всей группы
            address = bot_instance.get_address_by_name(point_name)

            for order in point_orders:
                try:
                    order_id = str(order['ID'])
                    logger.info(f"Обработка заказа: ID={order_id}, полные данные={order}")

                    if not order_id or order_id == '':
                        logger.error(f"Пустой ID заказа! Данные заказа: {order}")
                        continue

                    summa = float(order['Сумма']) if order['Сумма'] else 0
                    quantity = order['Количество']
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка конвертации данных заказа: {order}, ошибка: {e}")
                    continue

                text = (
                    f"🔸 <b>Заказ #{order_id}</b>\n"
                    f"📍 {point_name}\n"
                )
                if address:
                    text += f"🏠 {address}\n"
                text += (
                    f"☕ {order['Товар']} × {quantity} кг\n"
                    f"💰 {summa:,.2f} грн"
                )

                keyboard = [
                    [
                        InlineKeyboardButton(
                            text=f"✏️ Редактировать",
                            callback_data=f"editorder_{order_id}"
                        ),
                        InlineKeyboardButton(
                            text=f"✅ Выполнить заказ #{order_id}",
                            callback_data=f"done_{order_id}"
                        )
                    ]
                ]

                reply_markup = InlineKeyboardMarkup(keyboard)

                logger.info(f"Создана кнопка с callback_data: done_{order_id}")
                await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)

    # Выполненные заказы, сгруппированные по адресу
    if done:
        text = "<b>✅ Выполнены:</b>\n\n"

        # Группируем по точке (адресу)
        from collections import defaultdict
        grouped_done = defaultdict(list)
        for order in done:
            point_name = order['Точка']
            grouped_done[point_name].append(order)

        # Выводим заказы сгруппированные по адресу
        for point_name in sorted(grouped_done.keys()):
            point_orders = grouped_done[point_name]
            address = bot_instance.get_address_by_name(point_name)

            text += f"📍 <b>{point_name}</b>\n"
            if address:
                text += f"🏠 {address}\n"
            text += "\n"

            for order in point_orders:
                try:
                    order_id = str(order['ID'])
                    summa = float(order['Сумма']) if order['Сумма'] else 0
                    quantity = order['Количество']
                    done_date = order.get('Дата выполнения', '')
                except (ValueError, TypeError):
                    logger.error(f"Ошибка конвертации данных заказа: {order}")
                    continue

                text += (
                    f"  🔹 ID: {order_id}\n"
                    f"  ☕ {order['Товар']} × {quantity} кг\n"
                    f"  💰 {summa:,.2f} грн\n"
                )
                if done_date:
                    text += f"  ✓ {done_date}\n"
                text += "\n"

        await update.message.reply_text(text, parse_mode='HTML')

    return CHOOSING_ACTION


async def show_orders_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ заказов на завтра"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    orders = bot_instance.get_orders_by_date(tomorrow)

    if not orders:
        await update.message.reply_text("📅 На завтра заказов нет.")
        return CHOOSING_ACTION

    # Сортируем по дате создания (по возрастанию)
    orders.sort(key=lambda x: x.get('Дата создания', ''))

    # Разделяем на выполненные и ожидающие
    pending = [o for o in orders if o['Статус'] == 'Ожидает']
    done = [o for o in orders if o['Статус'] == 'Выполнен']

    # Отправляем заголовок
    await update.message.reply_text(f"📅 <b>Заказы на завтра ({tomorrow})</b>", parse_mode='HTML')

    # Группируем ожидающие заказы по адресу
    if pending:
        await update.message.reply_text("<b>⏳ Ожидают выполнения:</b>", parse_mode='HTML')

        # Группируем по точке (адресу)
        from collections import defaultdict
        grouped = defaultdict(list)
        for order in pending:
            point_name = order['Точка']
            grouped[point_name].append(order)

        # Выводим заказы сгруппированные по адресу
        for point_name in sorted(grouped.keys()):
            point_orders = grouped[point_name]

            # Получаем адрес один раз для всей группы
            address = bot_instance.get_address_by_name(point_name)

            for order in point_orders:
                try:
                    order_id = str(order['ID'])
                    logger.info(f"Обработка заказа (завтра): ID={order_id}, полные данные={order}")

                    if not order_id or order_id == '':
                        logger.error(f"Пустой ID заказа! Данные заказа: {order}")
                        continue

                    summa = float(order['Сумма']) if order['Сумма'] else 0
                    quantity = order['Количество']
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка конвертации данных заказа: {order}, ошибка: {e}")
                    continue

                text = (
                    f"🔸 <b>Заказ #{order_id}</b>\n"
                    f"📍 {point_name}\n"
                )
                if address:
                    text += f"🏠 {address}\n"
                text += (
                    f"☕ {order['Товар']} × {quantity} кг\n"
                    f"💰 {summa:,.2f} грн"
                )

                keyboard = [[InlineKeyboardButton(
                    f"✅ Выполнить заказ #{order_id}",
                    callback_data=f"done_{order_id}"
                    [InlineKeyboardButton(f"✏️ Редактировать", callback_data=f"editorder_{order_id}")]
                )]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                logger.info(f"Создана кнопка с callback_data: done_{order_id}")
                await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)

    # Выполненные заказы, сгруппированные по адресу
    if done:
        text = "<b>✅ Выполнены:</b>\n\n"

        # Группируем по точке (адресу)
        from collections import defaultdict
        grouped_done = defaultdict(list)
        for order in done:
            point_name = order['Точка']
            grouped_done[point_name].append(order)

        # Выводим заказы сгруппированные по адресу
        for point_name in sorted(grouped_done.keys()):
            point_orders = grouped_done[point_name]
            address = bot_instance.get_address_by_name(point_name)

            text += f"📍 <b>{point_name}</b>\n"
            if address:
                text += f"🏠 {address}\n"
            text += "\n"

            for order in point_orders:
                try:
                    order_id = str(order['ID'])
                    summa = float(order['Сумма']) if order['Сумма'] else 0
                    quantity = order['Количество']
                    done_date = order.get('Дата выполнения', '')
                except (ValueError, TypeError):
                    logger.error(f"Ошибка конвертации данных заказа: {order}")
                    continue

                text += (
                    f"  🔹 ID: {order_id}\n"
                    f"  ☕ {order['Товар']} × {quantity} кг\n"
                    f"  💰 {summa:,.2f} грн\n"
                )
                if done_date:
                    text += f"  ✓ {done_date}\n"
                text += "\n"

        await update.message.reply_text(text, parse_mode='HTML')

    return CHOOSING_ACTION


async def mark_order_as_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отметка заказа как выполненного"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("done_"):
        try:
            order_id_str = query.data.split("_")[1]
            if not order_id_str:
                await query.answer("❌ Ошибка: не указан ID заказа", show_alert=True)
                logger.error(f"Пустой order_id в callback_data: {query.data}")
                return CHOOSING_ACTION

            order_id = int(order_id_str)
        except (ValueError, IndexError) as e:
            await query.answer("❌ Ошибка: неверный формат ID заказа", show_alert=True)
            logger.error(f"Ошибка парсинга order_id из callback_data '{query.data}': {e}")
            return CHOOSING_ACTION

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name

        # Получаем информацию о заказе ДО его выполнения
        today = datetime.now().strftime('%Y-%m-%d')
        orders = bot_instance.get_orders_by_date(today)
        order_info = next((o for o in orders if str(o['ID']) == str(order_id)), None)

        success, order_sum = bot_instance.mark_order_done(order_id, user_id, user_name)

        if success:
            cash = bot_instance.get_manager_cash(user_id)

            # Получаем текущий остаток товара
            message_text = (
                f"✅ Заказ #{order_id} отмечен как выполненный!\n\n"
                f"💵 Добавлено в кассу: {order_sum:,.2f} грн\n"
                f"💼 Касса на руках: {cash:,.2f} грн\n"
            )

            # Добавляем информацию об остатках, если удалось получить данные заказа
            if order_info:
                product_name = order_info.get('Товар', '')
                quantity = order_info.get('Количество', 0)

                if product_name:
                    stock = bot_instance.get_stock()
                    product_stock = next((s for s in stock if s['Товар'] == product_name), None)

                    if product_stock:
                        current_qty = product_stock['Количество']
                        min_qty = product_stock['Мин. остаток']

                        message_text += f"\n📦 Списано со склада: {product_name} - {quantity} кг\n"
                        message_text += f"📊 Остаток на складе: {current_qty:.1f} кг\n"

                        # Предупреждение о низком остатке
                        if current_qty <= 0:
                            message_text += "❌ <b>Товар закончился на складе!</b>\n"
                        elif current_qty <= min_qty:
                            message_text += f"⚠️ <b>Низкий остаток! Минимум: {min_qty:.1f} кг</b>\n"

            message_text += "\nИспользуйте кнопки в меню для просмотра остальных заказов."

            await query.answer(f"✅ Заказ #{order_id} выполнен! +{order_sum:,.2f} грн", show_alert=True)
            await query.edit_message_text(message_text, parse_mode='HTML')
        else:
            await query.answer("❌ Ошибка при обновлении заказа", show_alert=True)

    elif query.data == "refresh_today":
        # Обновляем список заказов на сегодня
        today = datetime.now().strftime('%Y-%m-%d')
        orders = bot_instance.get_orders_by_date(today)

        pending = [o for o in orders if o['Статус'] == 'Ожидает']
        done = [o for o in orders if o['Статус'] == 'Выполнен']

        text = f"📋 <b>Заказы на сегодня ({today})</b>\n\n"

        if pending:
            text += "<b>⏳ Ожидают выполнения:</b>\n\n"
            for order in pending:
                text += (
                    f"🔸 ID: {order['ID']}\n"
                    f"📍 {order['Точка']}\n"
                    f"☕ {order['Товар']} × {order['Количество']} шт.\n"
                    f"💰 {order['Сумма']:,.2f} грн\n\n"
                )

        if done:
            text += "<b>✅ Выполнены:</b>\n\n"
            for order in done:
                text += (
                    f"🔹 ID: {order['ID']}\n"
                    f"📍 {order['Точка']}\n"
                    f"☕ {order['Товар']} × {order['Количество']} шт.\n"
                    f"💰 {order['Сумма']:,.2f} грн\n"
                    f"✓ {order['Дата выполнения']}\n\n"
                )

        if pending:
            keyboard = []
            for order in pending[:10]:
                keyboard.append([InlineKeyboardButton(
                    f"✅ Выполнить #{order['ID']} - {order['Точка']}",
                    callback_data=f"done_{order['ID']}"
                )])
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="refresh_today")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await query.edit_message_text(text, parse_mode='HTML')

    elif query.data == "refresh_tomorrow":
        # Аналогично для завтра
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        orders = bot_instance.get_orders_by_date(tomorrow)

        pending = [o for o in orders if o['Статус'] == 'Ожидает']
        done = [o for o in orders if o['Статус'] == 'Выполнен']

        text = f"📅 <b>Заказы на завтра ({tomorrow})</b>\n\n"

        if pending:
            text += "<b>⏳ Ожидают выполнения:</b>\n\n"
            for order in pending:
                text += (
                    f"🔸 ID: {order['ID']}\n"
                    f"📍 {order['Точка']}\n"
                    f"☕ {order['Товар']} × {order['Количество']} шт.\n"
                    f"💰 {order['Сумма']:,.2f} грн\n\n"
                )

        if done:
            text += "<b>✅ Выполнены:</b>\n\n"
            for order in done:
                text += (
                    f"🔹 ID: {order['ID']}\n"
                    f"📍 {order['Точка']}\n"
                    f"☕ {order['Товар']} × {order['Количество']} шт.\n"
                    f"💰 {order['Сумма']:,.2f} грн\n"
                    f"✓ {order['Дата выполнения']}\n\n"
                )

        if pending:
            keyboard = []
            for order in pending[:10]:
                keyboard.append([InlineKeyboardButton(
                    f"✅ Выполнить #{order['ID']} - {order['Точка']}",
                    callback_data=f"done_{order['ID']}"
                )])
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="refresh_tomorrow")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await query.edit_message_text(text, parse_mode='HTML')

    return CHOOSING_ACTION


# ========== КАССА МЕНЕДЖЕРА ==========

async def show_my_cash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ кассы менеджера"""
    user_id = update.effective_user.id
    cash = bot_instance.get_manager_cash(user_id)

    await update.message.reply_text(
        f"💼 <b>Ваша касса</b>\n\n"
        f"💵 На руках: {cash:,.2f} грн",
        parse_mode='HTML'
    )

    return CHOOSING_ACTION


async def handle_add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка добавления расхода"""
    try:
        text = update.message.text.strip()

        # Проверка на отмену
        if text.lower() in ['/q', 'q', '/cancel', 'cancel']:
            await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
            return CHOOSING_ACTION

        parts = text.split(',')
        if len(parts) != 2:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: Описание, Сумма\n"
                "Например: Транспорт, 500\n\n"
                "Введите /q для выхода в главное меню."
            )
            return ADD_EXPENSE

        description = parts[0].strip()
        amount = float(parts[1].strip())

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше нуля.")
            return ADD_EXPENSE

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name

        # Проверяем достаточно ли денег
        current_cash = bot_instance.get_manager_cash(user_id)
        if current_cash < amount:
            await update.message.reply_text(
                f"❌ Недостаточно средств в кассе!\n"
                f"💵 Доступно: {current_cash:,.2f} грн\n"
                f"💰 Требуется: {amount:,.2f} грн"
            )
            return CHOOSING_ACTION

        if bot_instance.add_expense(user_id, user_name, description, amount):
            new_cash = bot_instance.get_manager_cash(user_id)
            await update.message.reply_text(
                f"✅ Расход добавлен!\n\n"
                f"📝 Описание: {description}\n"
                f"💰 Сумма: {amount:,.2f} грн\n"
                f"💼 Остаток в кассе: {new_cash:,.2f} грн"
            )
        else:
            await update.message.reply_text("❌ Ошибка при сохранении расхода.")

        return CHOOSING_ACTION

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат суммы. Попробуйте снова:\n"
            "Например: Транспорт, 500\n\n"
            "Введите /q для выхода в главное меню."
        )
        return ADD_EXPENSE


async def handle_cash_handover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сдачи кассы"""
    try:
        text = update.message.text.strip()

        # Проверка на отмену
        if text.lower() in ['/q', 'q', '/cancel', 'cancel']:
            await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
            return CHOOSING_ACTION

        amount = float(text)

        if amount <= 0:
            await update.message.reply_text(
                "❌ Сумма должна быть больше нуля.\n\n"
                "Введите /q для выхода в главное меню."
            )
            return CASH_HANDOVER

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name

        success, result = bot_instance.handover_cash(user_id, user_name, amount)

        if success:
            await update.message.reply_text(
                f"✅ Касса сдана!\n\n"
                f"💵 Сдано: {amount:,.2f} грн\n"
                f"💼 Остаток в кассе: {result:,.2f} грн"
            )
        else:
            await update.message.reply_text(f"❌ Ошибка: {result}")

        return CHOOSING_ACTION

    except ValueError:
        await update.message.reply_text(
            "❌ Введите корректное число:\n\n"
            "Введите /q для выхода в главное меню."
        )
        return CASH_HANDOVER


# ========== СТАТИСТИКА ==========

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики"""
    daily_total = bot_instance.get_daily_total()
    monthly_total = bot_instance.get_monthly_total()
    monthly_expenses = bot_instance.get_monthly_expenses()
    monthly_profit = monthly_total - monthly_expenses

    # Для менеджеров показываем кассу
    user_id = update.effective_user.id
    role = bot_instance.get_user_role(user_id)

    stats_text = (
        f"📊 <b>Статистика</b>\n\n"
        f"📅 <b>За сегодня:</b>\n"
        f"Выручка: {daily_total:,.2f} грн\n\n"
        f"📆 <b>За текущий месяц:</b>\n"
        f"Выручка: {monthly_total:,.2f} грн\n"
        f"Расходы: {monthly_expenses:,.2f} грн\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💵 <b>Прибыль: {monthly_profit:,.2f} грн</b>"
    )

    if role in [ROLE_MANAGER, ROLE_OWNER, ROLE_DEVELOPER]:
        cash = bot_instance.get_manager_cash(user_id)
        stats_text += f"\n\n💼 <b>Ваша касса: {cash:,.2f} грн</b>"

    await update.message.reply_text(stats_text, parse_mode='HTML')
    return CHOOSING_ACTION


# ========== УПРАВЛЕНИЕ АДРЕСАМИ И ТОВАРАМИ (упрощенно) ==========

async def manage_addresses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление адресами"""
    logger.info("Вызвана функция manage_addresses")
    keyboard = [
        [InlineKeyboardButton("➕ Добавить адрес", callback_data="add_address")],
        [InlineKeyboardButton("✏️ Редактировать адрес", callback_data="edit_address")],
        [InlineKeyboardButton("🗑️ Удалить адрес", callback_data="delete_address")],
        [InlineKeyboardButton("📋 Список адресов", callback_data="list_addresses")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📍 Управление адресами:", reply_markup=reply_markup)
    logger.info("Отправлено сообщение с кнопками управления адресами")
    return CHOOSING_ACTION


async def manage_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление товарами"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton("✏️ Редактировать товар", callback_data="edit_product")],
        [InlineKeyboardButton("🗑️ Удалить товар", callback_data="delete_product")],
        [InlineKeyboardButton("📋 Список товаров", callback_data="list_products")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("☕ Управление товарами:", reply_markup=reply_markup)
    return CHOOSING_ACTION


async def manage_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление остатками"""
    stock = bot_instance.get_stock()

    text = "📦 <b>Текущие остатки:</b>\n\n"

    if stock:
        for item in stock:
            qty = item['Количество']
            min_qty = item['Мин. остаток']

            # Определяем статус остатка
            if qty <= 0:
                status = "❌"
            elif qty <= min_qty:
                status = "⚠️"
            else:
                status = "✅"

            text += f"{status} <b>{item['Товар']}</b>\n"
            text += f"   Остаток: {qty:.1f} кг\n"
            text += f"   Минимум: {min_qty:.1f} кг\n\n"
    else:
        text += "Остатки пока не добавлены\n\n"

    keyboard = [
        [InlineKeyboardButton("➕ Добавить поступление", callback_data="add_stock_arrival")],
        [InlineKeyboardButton("➖ Списать товар", callback_data="write_off_stock")],
        [InlineKeyboardButton("⚙️ Установить минимум", callback_data="set_min_stock")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
    return CHOOSING_ACTION


async def handle_management_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка колбэков управления"""
    query = update.callback_query
    await query.answer()

    logger.info(f"handle_management_callbacks вызван с callback_data: {query.data}")

    # ========== УПРАВЛЕНИЕ ОСТАТКАМИ ==========

    if query.data == "add_stock_arrival":
        # Добавление поступления товара
        products = bot_instance.get_products()
        if not products:
            await query.edit_message_text("❌ Сначала добавьте товары в каталог")
            return CHOOSING_ACTION

        keyboard = []
        # Показываем все товары (убрали ограничение [:10])
        for prod in products:
            keyboard.append([InlineKeyboardButton(
                f"{prod['Название']} ({prod['Вес']})",
                callback_data=f"arrival_{prod['ID']}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_stock")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "➕ <b>Добавить поступление</b>\n\n"
            "Выберите товар:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return CHOOSING_ACTION

    elif query.data.startswith("arrival_"):
        product_id = int(query.data.split("_")[1])
        products = bot_instance.get_products()
        product = next((p for p in products if p['ID'] == product_id), None)

        if product:
            context.user_data['stock_product'] = product['Название']
            context.user_data['stock_action'] = 'arrival'

            stock = bot_instance.get_stock()
            current = next((s for s in stock if s['Товар'] == product['Название']), None)
            current_qty = current['Количество'] if current else 0

            await query.edit_message_text(
                f"➕ <b>Поступление товара</b>\n\n"
                f"📦 Товар: <b>{product['Название']}</b>\n"
                f"📊 Текущий остаток: {current_qty:.1f} кг\n\n"
                f"Введите количество кг для добавления:\n"
                f"Например: 50",
                parse_mode='HTML'
            )
            return STOCK_ARRIVAL
        return CHOOSING_ACTION

    elif query.data == "write_off_stock":
        # Списание товара
        stock = bot_instance.get_stock()
        if not stock:
            await query.edit_message_text("❌ Остатки пока не добавлены")
            return CHOOSING_ACTION

        keyboard = []
        for item in stock:
            if item['Количество'] > 0:  # Показываем только товары с остатком
                keyboard.append([InlineKeyboardButton(
                    f"{item['Товар']}: {item['Количество']:.1f} кг",
                    callback_data=f"writeoff_{item['Товар']}"
                )])

        if not keyboard:
            await query.edit_message_text("❌ Нет товаров для списания")
            return CHOOSING_ACTION

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_stock")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "➖ <b>Списание товара</b>\n\n"
            "Выберите товар:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return CHOOSING_ACTION

    elif query.data.startswith("writeoff_"):
        product_name = query.data.replace("writeoff_", "")
        context.user_data['stock_product'] = product_name
        context.user_data['stock_action'] = 'writeoff'

        stock = bot_instance.get_stock()
        current = next((s for s in stock if s['Товар'] == product_name), None)
        current_qty = current['Количество'] if current else 0

        await query.edit_message_text(
            f"➖ <b>Списание товара</b>\n\n"
            f"📦 Товар: <b>{product_name}</b>\n"
            f"📊 Текущий остаток: {current_qty:.1f} кг\n\n"
            f"Введите количество кг для списания:\n"
            f"Например: 5",
            parse_mode='HTML'
        )
        return STOCK_WRITEOFF

    elif query.data == "set_min_stock":
        # Установка минимального остатка
        products = bot_instance.get_products()
        if not products:
            await query.edit_message_text("❌ Сначала добавьте товары в каталог")
            return CHOOSING_ACTION

        stock = bot_instance.get_stock()

        keyboard = []
        for prod in products:
            # Проверяем текущий минимум из остатков
            current_stock = next((s for s in stock if s['Товар'] == prod['Название']), None)
            current_min = current_stock['Мін. остаток'] if current_stock else 0

            keyboard.append([InlineKeyboardButton(
                f"{prod['Название']}: мин. {current_min:.1f} кг",
                callback_data=f"setmin_{prod['Название']}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_stock")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "⚙️ <b>Установить минимальный остаток</b>\n\n"
            "Выберите товар:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return CHOOSING_ACTION

    elif query.data.startswith("setmin_"):
        product_name = query.data.replace("setmin_", "")
        context.user_data['stock_product'] = product_name
        context.user_data['stock_action'] = 'setmin'

        stock = bot_instance.get_stock()
        current = next((s for s in stock if s['Товар'] == product_name), None)
        current_min = current['Мін. остаток'] if current else 0

        await query.edit_message_text(
            f"⚙️ <b>Минимальный остаток</b>\n\n"
            f"📦 Товар: <b>{product_name}</b>\n"
            f"⚠️ Текущий минимум: {current_min:.1f} кг\n\n"
            f"Введите новый минимальный остаток в кг:\n"
            f"Например: 10",
            parse_mode='HTML'
        )
        return SET_MIN_STOCK

    elif query.data == "back_stock":
        # Возврат к меню остатков
        stock = bot_instance.get_stock()

        text = "📦 <b>Текущие остатки:</b>\n\n"

        if stock:
            for item in stock:
                qty = item['Количество']
                min_qty = item['Мин. остаток']

                if qty <= 0:
                    status = "❌"
                elif qty <= min_qty:
                    status = "⚠️"
                else:
                    status = "✅"

                text += f"{status} <b>{item['Товар']}</b>\n"
                text += f"   Остаток: {qty:.1f} кг\n"
                text += f"   Минимум: {min_qty:.1f} кг\n\n"
        else:
            text += "Остатки пока не добавлены\n\n"

        keyboard = [
            [InlineKeyboardButton("➕ Добавить поступление", callback_data="add_stock_arrival")],
            [InlineKeyboardButton("➖ Списать товар", callback_data="write_off_stock")],
            [InlineKeyboardButton("⚙️ Установить минимум", callback_data="set_min_stock")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
        return CHOOSING_ACTION

    elif query.data == "add_address":
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Введите данные через запятую:\n"
            "Название, Адрес, Контакт (необязательно)\n\n"
            "Примеры:\n"
            "• Кофейня Новая, ул. Пушкина 15, Иван +380501234567\n"
            "• Кофейня Новая, ул. Пушкина 15",
            reply_markup=reply_markup
        )
        return ADD_ADDRESS

    elif query.data == "list_addresses":
        addresses = bot_instance.get_addresses()
        if not addresses:
            await query.edit_message_text("❌ Список адресов пуст.")
        else:
            text = "📋 <b>Список адресов:</b>\n\n"
            for addr in addresses:
                text += f"🔹 {addr['Название']}\n   {addr['Адрес']}\n\n"
            await query.edit_message_text(text, parse_mode='HTML')
        return CHOOSING_ACTION

    elif query.data == "edit_address":
        # Редактирование адреса - показываем список для выбора
        addresses = bot_instance.get_addresses()
        if not addresses:
            await query.edit_message_text("❌ Список адресов пуст.")
            return CHOOSING_ACTION

        keyboard = []
        for addr in addresses:
            # Показываем название И адрес
            keyboard.append([InlineKeyboardButton(
                f"✏️ {addr['Название']} - {addr['Адрес']}",
                callback_data=f"editaddr_{addr['ID']}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "✏️ <b>Редактировать адрес</b>\n\n"
            "Выберите адрес:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return EDIT_ADDRESS_SELECT

    elif query.data.startswith("editaddr_"):
        # Показать текущие данные адреса и запросить новые
        address_id = int(query.data.split("_")[1])
        addresses = bot_instance.get_addresses()
        address = next((a for a in addresses if a['ID'] == address_id), None)

        if address:
            context.user_data['edit_address_id'] = address_id
            context.user_data['edit_address'] = address

            msg = (
                f"✏️ <b>Редактирование адреса</b>\n\n"
                f"<b>Текущие данные:</b>\n"
                f"📍 Название: {address['Название']}\n"
                f"🏠 Адрес: {address['Адрес']}\n"
            )
            if address.get('Контакт'):
                msg += f"👤 Контакт: {address['Контакт']}\n"

            msg += (
                f"\nВведите новые данные через запятую:\n"
                f"Название, Адрес, Контакт (необязательно)\n\n"
                f"Например:\n"
                f"Кофейня Новая, ул. Пушкина 15, Иван +380501234567\n\n"
                f"Введите /q для отмены."
            )

            await query.edit_message_text(msg, parse_mode='HTML')
            return EDIT_ADDRESS_DATA

        return CHOOSING_ACTION

    elif query.data == "edit_address":
        # Редактирование адреса - показываем список адресов
        addresses = bot_instance.get_addresses()
        if not addresses:
            await query.edit_message_text("❌ Список адресов пуст.")
            return CHOOSING_ACTION

        keyboard = []
        for addr in addresses:
            keyboard.append([InlineKeyboardButton(
                f"✏️ {addr['Название']} - {addr['Адрес']}",
                callback_data=f"editaddr_{addr['ID']}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "✏️ <b>Редактировать адрес</b>\n\n"
            "Выберите адрес для редактирования:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return EDIT_ADDRESS_SELECT

    elif query.data.startswith("editaddr_"):
        # Обработка выбора адреса для редактирования
        address_id = int(query.data.split("_")[1])
        addresses = bot_instance.get_addresses()
        address = next((a for a in addresses if a['ID'] == address_id), None)

        if address:
            context.user_data['edit_address_id'] = address_id
            context.user_data['edit_address'] = address

            msg = (
                f"✏️ <b>Редактирование адреса</b>\n\n"
                f"Текущие данные:\n"
                f"📍 Название: {address['Название']}\n"
                f"🏠 Адрес: {address['Адрес']}\n"
            )
            if address.get('Контакт'):
                msg += f"👤 Контакт: {address['Контакт']}\n"

            msg += (
                f"\nВведите новые данные через запятую:\n"
                f"Название, Адрес, Контакт (необязательно)\n\n"
                f"Например:\n"
                f"Кофейня Новая, ул. Пушкина 15, Иван +380501234567\n"
                f"или: Кофейня Новая, ул. Пушкина 15"
            )

            await query.edit_message_text(msg, parse_mode='HTML')
            return EDIT_ADDRESS_DATA
        return CHOOSING_ACTION

    elif query.data == "delete_address":
        # Удаление адреса - показываем список адресов для выбора
        addresses = bot_instance.get_addresses()
        if not addresses:
            await query.edit_message_text("❌ Список адресов пуст.")
            return CHOOSING_ACTION

        keyboard = []
        for addr in addresses:
            keyboard.append([InlineKeyboardButton(
                f"🗑️ {addr['Название']} - {addr['Адрес']}",
                callback_data=f"deladdr_{addr['ID']}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🗑️ <b>Удалить адрес</b>\n\n"
            "⚠️ Выберите адрес для удаления:\n"
            "(Это действие нельзя отменить)",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return DELETE_ADDRESS_SELECT

    elif query.data.startswith("deladdr_"):
        # Обработка удаления адреса
        address_id = int(query.data.split("_")[1])
        addresses = bot_instance.get_addresses()
        address = next((a for a in addresses if a['ID'] == address_id), None)

        if address:
            # Запрашиваем подтверждение
            keyboard = [
                [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirmdeladdr_{address_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"⚠️ <b>Подтвердите удаление</b>\n\n"
                f"Вы точно хотите удалить адрес?\n\n"
                f"📍 {address['Название']}\n"
                f"🏠 {address['Адрес']}",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return DELETE_ADDRESS_SELECT
        return CHOOSING_ACTION

    elif query.data.startswith("confirmdeladdr_"):
        # Подтверждение удаления адреса
        address_id = int(query.data.split("_")[1])
        addresses = bot_instance.get_addresses()
        address = next((a for a in addresses if a['ID'] == address_id), None)

        if address and bot_instance.delete_address(address_id):
            await query.edit_message_text(
                f"✅ Адрес успешно удален!\n\n"
                f"📍 {address['Название']}\n"
                f"🏠 {address['Адрес']}\n\n"
                f"Используйте /start для возврата в меню."
            )
        else:
            await query.edit_message_text("❌ Ошибка при удалении адреса.")

        return CHOOSING_ACTION

    elif query.data == "add_product":
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Введите данные товара через запятую:\n"
            "Название, Вес, Розница, Опт, VIP\n\n"
            "Например: Арабика, 1кг, 850, 750, 650",
            reply_markup=reply_markup
        )
        return ADD_PRODUCT_DATA

    elif query.data == "list_products":
        products = bot_instance.get_products()
        if not products:
            await query.edit_message_text("❌ Список товаров пуст.")
        else:
            text = "📋 <b>Список товаров:</b>\n\n"
            for prod in products:
                text += f"☕ {prod['Название']} - {prod['Вес']}\n"
                text += f"   🛍️ Розница: {prod.get('Цена розница', 0)} грн\n"
                text += f"   📦 Опт: {prod.get('Цена опт', 0)} грн\n"
                text += f"   ⭐ VIP: {prod.get('Цена VIP', 0)} грн\n\n"
            await query.edit_message_text(text, parse_mode='HTML')
        return CHOOSING_ACTION

    elif query.data == "edit_product":
        # Редактирование товара - показываем список товаров для выбора
        products = bot_instance.get_products()
        if not products:
            await query.edit_message_text("❌ Список товаров пуст.")
            return CHOOSING_ACTION

        keyboard = []
        for prod in products:
            keyboard.append([InlineKeyboardButton(
                f"{prod['Название']} ({prod['Вес']})",
                callback_data=f"editprod_{prod['ID']}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "✏️ <b>Редактировать товар</b>\n\n"
            "Выберите товар для редактирования:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return EDIT_PRODUCT_SELECT

    elif query.data.startswith("editprod_"):
        # Обработка выбора товара для редактирования
        product_id = int(query.data.split("_")[1])
        products = bot_instance.get_products()
        product = next((p for p in products if p['ID'] == product_id), None)

        if product:
            context.user_data['edit_product_id'] = product_id
            context.user_data['edit_product'] = product

            await query.edit_message_text(
                f"✏️ <b>Редактирование товара</b>\n\n"
                f"Текущие данные:\n"
                f"☕ Название: {product['Название']}\n"
                f"📏 Вес: {product['Вес']}\n"
                f"💰 Розница: {product.get('Цена розница', 0)} грн\n"
                f"💰 Опт: {product.get('Цена опт', 0)} грн\n"
                f"💰 VIP: {product.get('Цена VIP', 0)} грн\n\n"
                f"Введите новые данные через запятую:\n"
                f"Название, Вес, Розница, Опт, VIP\n\n"
                f"Например: Арабика Премиум, 1кг, 900, 800, 700",
                parse_mode='HTML'
            )
            return EDIT_PRODUCT_DATA
        return CHOOSING_ACTION

    elif query.data == "delete_product":
        # Удаление товара - показываем список товаров для выбора
        products = bot_instance.get_products()
        if not products:
            await query.edit_message_text("❌ Список товаров пуст.")
            return CHOOSING_ACTION

        keyboard = []
        for prod in products:
            keyboard.append([InlineKeyboardButton(
                f"🗑️ {prod['Название']} ({prod['Вес']})",
                callback_data=f"delprod_{prod['ID']}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🗑️ <b>Удалить товар</b>\n\n"
            "⚠️ Выберите товар для удаления:\n"
            "(Это действие нельзя отменить)",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return DELETE_PRODUCT_SELECT

    elif query.data.startswith("delprod_"):
        # Обработка удаления товара
        product_id = int(query.data.split("_")[1])
        products = bot_instance.get_products()
        product = next((p for p in products if p['ID'] == product_id), None)

        if product:
            # Запрашиваем подтверждение
            keyboard = [
                [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirmdel_{product_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"⚠️ <b>Подтвердите удаление</b>\n\n"
                f"Вы точно хотите удалить товар?\n\n"
                f"☕ {product['Название']} - {product['Вес']}\n"
                f"💰 Розница: {product.get('Цена розница', 0)} грн\n"
                f"💰 Опт: {product.get('Цена опт', 0)} грн\n"
                f"💰 VIP: {product.get('Цена VIP', 0)} грн",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return DELETE_PRODUCT_SELECT
        return CHOOSING_ACTION

    elif query.data.startswith("confirmdel_"):
        # Подтверждение удаления товара
        product_id = int(query.data.split("_")[1])
        products = bot_instance.get_products()
        product = next((p for p in products if p['ID'] == product_id), None)

        if product and bot_instance.delete_product(product_id):
            await query.edit_message_text(
                f"✅ Товар успешно удален!\n\n"
                f"☕ {product['Название']} - {product['Вес']}\n\n"
                f"Используйте /start для возврата в меню."
            )
        else:
            await query.edit_message_text("❌ Ошибка при удалении товара.")

        return CHOOSING_ACTION

    return CHOOSING_ACTION


async def handle_add_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка добавления адреса"""
    try:
        # Проверка на отмену
        text = update.message.text.strip()
        if text.lower() in ['/q', 'q', '/cancel', 'cancel']:
            await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
            return CHOOSING_ACTION

        parts = text.split(',')
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: Название, Адрес, Контакт (необязательно)\n\n"
                "Например:\n"
                "Кофейня Центральная, ул. Ленина 10, Иван +380501234567\n"
                "или: Кофейня Центральная, ул. Ленина 10\n\n"
                "Введите /q для выхода в главное меню."
            )
            return ADD_ADDRESS

        name = parts[0].strip()
        address = parts[1].strip()
        contact = parts[2].strip() if len(parts) > 2 else ''

        if bot_instance.add_address(name, address, contact):
            msg = f"✅ Адрес успешно добавлен!\n\n📍 Название: {name}\n🏠 Адрес: {address}"
            if contact:
                msg += f"\n👤 Контакт: {contact}"
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("❌ Ошибка при добавлении адреса.")

        return CHOOSING_ACTION

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return ADD_ADDRESS


async def handle_edit_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка редактирования адреса"""
    try:
        text = update.message.text.strip()

        # Проверка на отмену
        if text.lower() in ['/q', 'q', '/cancel', 'cancel']:
            await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
            context.user_data.pop('edit_address_id', None)
            context.user_data.pop('edit_address', None)
            return CHOOSING_ACTION

        parts = text.split(',')
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: Название, Адрес, Контакт (необязательно)\n\n"
                "Например:\n"
                "Кофейня Новая, ул. Пушкина 15, Петр +380501234567\n"
                "или: Кофейня Новая, ул. Пушкина 15\n\n"
                "Введите /q для выхода в главное меню."
            )
            return EDIT_ADDRESS_DATA

        name = parts[0].strip()
        address = parts[1].strip()
        contact = parts[2].strip() if len(parts) > 2 else ''

        address_id = context.user_data.get('edit_address_id')
        old_address = context.user_data.get('edit_address')

        if bot_instance.update_address(address_id, name, address, contact):
            msg = (
                f"✅ Адрес успешно обновлен!\n\n"
                f"<b>Было:</b>\n"
                f"📍 {old_address['Название']}\n"
                f"🏠 {old_address['Адрес']}\n"
            )
            if old_address.get('Контакт'):
                msg += f"👤 {old_address['Контакт']}\n"

            msg += f"\n<b>Стало:</b>\n📍 {name}\n🏠 {address}\n"
            if contact:
                msg += f"👤 {contact}"

            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text("❌ Ошибка при обновлении адреса.")

        context.user_data.pop('edit_address_id', None)
        context.user_data.pop('edit_address', None)
        return CHOOSING_ACTION

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return EDIT_ADDRESS_DATA


async def handle_edit_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка редактирования адреса"""
    try:
        # Проверка на отмену
        text = update.message.text.strip()
        if text.lower() in ['/q', 'q', '/cancel', 'cancel']:
            context.user_data.pop('edit_address_id', None)
            context.user_data.pop('edit_address', None)
            await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
            return CHOOSING_ACTION

        parts = text.split(',')
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: Название, Адрес, Контакт (необязательно)\n\n"
                "Например:\n"
                "Кофейня Новая, ул. Пушкина 15, Иван +380501234567\n"
                "или: Кофейня Новая, ул. Пушкина 15\n\n"
                "Введите /q для выхода в главное меню."
            )
            return EDIT_ADDRESS_DATA

        name = parts[0].strip()
        address = parts[1].strip()
        contact = parts[2].strip() if len(parts) > 2 else ''

        address_id = context.user_data.get('edit_address_id')
        old_address = context.user_data.get('edit_address')

        if bot_instance.update_address(address_id, name, address, contact):
            msg = (
                f"✅ Адрес успешно обновлен!\n\n"
                f"<b>Было:</b>\n"
                f"📍 {old_address['Название']}\n"
                f"🏠 {old_address['Адрес']}\n"
            )
            if old_address.get('Контакт'):
                msg += f"👤 {old_address['Контакт']}\n"

            msg += f"\n<b>Стало:</b>\n📍 {name}\n🏠 {address}\n"
            if contact:
                msg += f"👤 {contact}"

            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text("❌ Ошибка при обновлении адреса.")

        context.user_data.pop('edit_address_id', None)
        context.user_data.pop('edit_address', None)
        return CHOOSING_ACTION

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return EDIT_ADDRESS_DATA


async def handle_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка добавления товара"""
    try:
        # Проверка на отмену
        text = update.message.text.strip()
        if text.lower() in ['/q', 'q', '/cancel', 'cancel']:
            await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
            return CHOOSING_ACTION

        parts = text.split(',')
        if len(parts) != 5:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: Название, Вес, Розница, Опт, VIP\n"
                "Например: Арабика, 1кг, 850, 750, 650\n\n"
                "Введите /q для выхода в главное меню."
            )
            return ADD_PRODUCT_DATA

        name = parts[0].strip()
        weight = parts[1].strip()
        price_retail = float(parts[2].strip())
        price_wholesale = float(parts[3].strip())
        price_vip = float(parts[4].strip())

        if price_retail <= 0 or price_wholesale <= 0 or price_vip <= 0:
            await update.message.reply_text(
                "❌ Все цены должны быть больше нуля.\n\n"
                "Попробуйте снова или введите /q для выхода."
            )
            return ADD_PRODUCT_DATA

        if bot_instance.add_product(name, weight, price_retail, price_wholesale, price_vip):
            await update.message.reply_text(
                f"✅ Товар успешно добавлен!\n\n"
                f"☕ Название: {name}\n"
                f"📏 Вес: {weight}\n"
                f"💰 Розница: {price_retail} грн\n"
                f"💰 Опт: {price_wholesale} грн\n"
                f"💰 VIP: {price_vip} грн"
            )
        else:
            await update.message.reply_text("❌ Ошибка при добавлении товара.")

        return CHOOSING_ACTION

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат цен. Используйте числа.\n\n"
            "Введите /q для выхода в главное меню."
        )
        return ADD_PRODUCT_DATA


async def handle_edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка редактирования товара"""
    try:
        # Проверка на отмену
        text = update.message.text.strip()
        if text.lower() in ['/q', 'q', '/cancel', 'cancel']:
            await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
            context.user_data.pop('edit_product_id', None)
            context.user_data.pop('edit_product', None)
            return CHOOSING_ACTION

        parts = text.split(',')
        if len(parts) != 5:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: Название, Вес, Розница, Опт, VIP\n"
                "Например: Арабика Премиум, 1кг, 900, 800, 700\n\n"
                "Введите /q для выхода в главное меню."
            )
            return EDIT_PRODUCT_DATA

        name = parts[0].strip()
        weight = parts[1].strip()
        price_retail = float(parts[2].strip())
        price_wholesale = float(parts[3].strip())
        price_vip = float(parts[4].strip())

        if price_retail <= 0 or price_wholesale <= 0 or price_vip <= 0:
            await update.message.reply_text(
                "❌ Все цены должны быть больше нуля.\n\n"
                "Введите /q для выхода в главное меню."
            )
            return EDIT_PRODUCT_DATA

        product_id = context.user_data.get('edit_product_id')
        old_product = context.user_data.get('edit_product')

        if bot_instance.update_product(product_id, name, weight, price_retail, price_wholesale, price_vip):
            await update.message.reply_text(
                f"✅ Товар успешно обновлен!\n\n"
                f"<b>Было:</b>\n"
                f"☕ {old_product['Название']} - {old_product['Вес']}\n"
                f"💰 Розница: {old_product.get('Цена розница', 0)} грн\n"
                f"💰 Опт: {old_product.get('Цена опт', 0)} грн\n"
                f"💰 VIP: {old_product.get('Цена VIP', 0)} грн\n\n"
                f"<b>Стало:</b>\n"
                f"☕ {name} - {weight}\n"
                f"💰 Розница: {price_retail} грн\n"
                f"💰 Опт: {price_wholesale} грн\n"
                f"💰 VIP: {price_vip} грн",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Ошибка при обновлении товара.")

        context.user_data.pop('edit_product_id', None)
        context.user_data.pop('edit_product', None)
        return CHOOSING_ACTION

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат цен. Используйте числа.\n\n"
            "Введите /q для выхода в главное меню."
        )
        return EDIT_PRODUCT_DATA


async def handle_stock_arrival(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка добавления поступления"""
    try:
        quantity = float(update.message.text.strip())

        if quantity <= 0:
            await update.message.reply_text("❌ Количество должно быть больше нуля.")
            return STOCK_ARRIVAL

        product_name = context.user_data.get('stock_product')
        if not product_name:
            await update.message.reply_text("❌ Ошибка: товар не выбран.")
            return CHOOSING_ACTION

        # Добавляем к остаткам
        if bot_instance.update_stock(product_name, quantity):
            stock = bot_instance.get_stock()
            current = next((s for s in stock if s['Товар'] == product_name), None)
            new_qty = current['Количество'] if current else quantity

            await update.message.reply_text(
                f"✅ Поступление оформлено!\n\n"
                f"📦 Товар: {product_name}\n"
                f"➕ Добавлено: {quantity:.1f} кг\n"
                f"📊 Новый остаток: {new_qty:.1f} кг"
            )
        else:
            await update.message.reply_text("❌ Ошибка при обновлении остатка.")

        context.user_data.pop('stock_product', None)
        context.user_data.pop('stock_action', None)
        return CHOOSING_ACTION

    except ValueError:
        await update.message.reply_text("❌ Введите корректное число.")
        return STOCK_ARRIVAL


async def handle_stock_writeoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода количества для списания"""
    try:
        quantity = float(update.message.text.strip())

        if quantity <= 0:
            await update.message.reply_text("❌ Количество должно быть больше нуля.")
            return STOCK_WRITEOFF

        product_name = context.user_data.get('stock_product')
        if not product_name:
            await update.message.reply_text("❌ Ошибка: товар не выбран.")
            return CHOOSING_ACTION

        # Проверяем, достаточно ли остатка
        stock = bot_instance.get_stock()
        current = next((s for s in stock if s['Товар'] == product_name), None)
        if not current or current['Количество'] < quantity:
            await update.message.reply_text(
                f"❌ Недостаточно остатка!\n"
                f"Доступно: {current['Количество'] if current else 0:.1f} кг"
            )
            return STOCK_WRITEOFF

        # Сохраняем количество и запрашиваем причину
        context.user_data['writeoff_quantity'] = quantity
        await update.message.reply_text(
            f"📝 Укажите причину списания:\n\n"
            f"Например:\n"
            f"• Брак\n"
            f"• Просрочка\n"
            f"• Личное использование\n"
            f"• Дегустация\n"
            f"• Другое"
        )
        return STOCK_WRITEOFF_REASON

    except ValueError:
        await update.message.reply_text("❌ Введите корректное число.")
        return STOCK_WRITEOFF


async def handle_stock_writeoff_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка причины списания"""
    product_name = context.user_data.get('stock_product')
    quantity = context.user_data.get('writeoff_quantity')
    reason = update.message.text.strip()

    if not product_name or not quantity:
        await update.message.reply_text("❌ Ошибка: данные не найдены.")
        return CHOOSING_ACTION

    # Списываем остаток
    if bot_instance.update_stock(product_name, -quantity):
        stock = bot_instance.get_stock()
        current = next((s for s in stock if s['Товар'] == product_name), None)
        new_qty = current['Количество'] if current else 0

        await update.message.reply_text(
            f"✅ Товар списан!\n\n"
            f"📦 Товар: {product_name}\n"
            f"➖ Списано: {quantity:.1f} кг\n"
            f"📝 Причина: {reason}\n"
            f"📊 Остаток: {new_qty:.1f} кг"
        )
    else:
        await update.message.reply_text("❌ Ошибка при списании.")

    context.user_data.pop('stock_product', None)
    context.user_data.pop('writeoff_quantity', None)
    context.user_data.pop('stock_action', None)
    return CHOOSING_ACTION


async def handle_set_min_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка установки минимального остатка"""
    try:
        min_quantity = float(update.message.text.strip())

        if min_quantity < 0:
            await update.message.reply_text("❌ Минимум не может быть отрицательным.")
            return SET_MIN_STOCK

        product_name = context.user_data.get('stock_product')
        if not product_name:
            await update.message.reply_text("❌ Ошибка: товар не выбран.")
            return CHOOSING_ACTION

        # Обновляем минимальный остаток
        stock = bot_instance.get_stock()
        current = next((s for s in stock if s['Товар'] == product_name), None)
        current_qty = current['Количество'] if current else 0

        if bot_instance.set_stock(product_name, current_qty, min_quantity):
            await update.message.reply_text(
                f"✅ Минимальный остаток установлен!\n\n"
                f"📦 Товар: {product_name}\n"
                f"⚠️ Новый минимум: {min_quantity:.1f} кг\n"
                f"📊 Текущий остаток: {current_qty:.1f} кг"
            )
        else:
            await update.message.reply_text("❌ Ошибка при обновлении.")

        context.user_data.pop('stock_product', None)
        context.user_data.pop('stock_action', None)
        return CHOOSING_ACTION

    except ValueError:
        await update.message.reply_text("❌ Введите корректное число.")
        return SET_MIN_STOCK


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text("Операция отменена. Используйте /start для возврата в меню.")
    return ConversationHandler.END


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Общий обработчик кнопок"""
    query = update.callback_query
    await query.answer()

    logger.info(f"button_handler вызван с callback_data: {query.data}")

    if query.data == "cancel":
        await query.edit_message_text("Операция отменена. Используйте /start для возврата в меню.")
        return ConversationHandler.END

    elif query.data == "back_to_menu":
        await query.message.reply_text("Используйте /start для возврата в меню.")
        return ConversationHandler.END

    # Управление
    if query.data in ["add_address", "list_addresses", "edit_address", "delete_address", "add_product", "list_products",
                      "edit_product", "delete_product"] or \
            query.data.startswith("editprod_") or query.data.startswith("delprod_") or \
            query.data.startswith("confirmdel_") or query.data.startswith("deladdr_") or \
            query.data.startswith("confirmdeladdr_") or query.data.startswith("editaddr_"):
        logger.info(f"Вызов handle_management_callbacks для {query.data}")
        return await handle_management_callbacks(update, context)

    # Управление остатками
    if query.data in ["add_stock_arrival", "write_off_stock", "set_min_stock", "back_stock"] or \
            query.data.startswith("arrival_") or query.data.startswith("writeoff_") or query.data.startswith("setmin_"):
        return await handle_management_callbacks(update, context)

    # Заказы
    if query.data.startswith("done_") or query.data.startswith("refresh_"):
        return await mark_order_as_done(update, context)

    # Редактирование заказа
    if query.data.startswith("editorder_"):
        return await handle_edit_order(update, context)

    if query.data.startswith("edit_field_"):
        return await handle_edit_field_select(update, context)

    # Корзина товаров
    if query.data in ["add_more_products", "add_service", "proceed_to_delivery"]:
        return await handle_product_selection(update, context)

    # Выбор даты доставки
    if query.data.startswith("delivery_"):
        return await handle_delivery_date(update, context)

    return CHOOSING_ACTION


# ========== ИНИЦИАЛИЗАЦИЯ APPLICATION ==========

def setup_application():
    """Настройка и инициализация application"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не установлен")
        raise ValueError("TELEGRAM_BOT_TOKEN is required")

    application = Application.builder().token(token).build()

    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                CallbackQueryHandler(button_handler)
            ],
            SELECT_ADDRESS: [
                CallbackQueryHandler(handle_address_selection)
            ],
            SELECT_PRODUCT: [
                CallbackQueryHandler(handle_product_selection)
            ],
            ENTER_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quantity)
            ],
            ENTER_DELIVERY_DATE: [
                CallbackQueryHandler(handle_delivery_date),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_delivery_date)
            ],
            ENTER_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)
            ],
            EDIT_ORDER_SELECT: [
                CallbackQueryHandler(button_handler)
            ],
            EDIT_ORDER_FIELD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_field_value)
            ],
            ADD_EXPENSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_expense)
            ],
            CASH_HANDOVER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cash_handover)
            ],
            ADD_ADDRESS: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_address)
            ],
            EDIT_ADDRESS_SELECT: [
                CallbackQueryHandler(button_handler)
            ],
            EDIT_ADDRESS_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_address)
            ],
            DELETE_ADDRESS_SELECT: [
                CallbackQueryHandler(button_handler)
            ],
            ADD_PRODUCT_DATA: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_product)
            ],
            EDIT_PRODUCT_SELECT: [
                CallbackQueryHandler(button_handler)
            ],
            EDIT_PRODUCT_DATA: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_product)
            ],
            DELETE_PRODUCT_SELECT: [
                CallbackQueryHandler(button_handler)
            ],
            STOCK_ARRIVAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stock_arrival)
            ],
            STOCK_WRITEOFF: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stock_writeoff)
            ],
            STOCK_WRITEOFF_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stock_writeoff_reason)
            ],
            SET_MIN_STOCK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_min_stock)
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('q', cancel),
            CallbackQueryHandler(button_handler)
        ],
    )

    application.add_handler(conv_handler)
    return application


# Инициализация бота и application
bot_instance = CoffeeBot()
application = setup_application()

# Для обратной совместимости с локальным запуском
if __name__ == '__main__':
    use_webhook = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'

    if use_webhook:
        logger.info("Для webhook используйте: uvicorn main:app --host 0.0.0.0 --port 8080")
        logger.info("Или запустите: python main.py")
    else:
        logger.info("Бот запущен в режиме POLLING (для локальной разработки)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)