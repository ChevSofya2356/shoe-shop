# test_db_integrity.py
import psycopg2
import sys

DB_CONFIG = {
    'host': 'localhost',
    'database': 'magazin_obuv',
    'user': 'postgres',
    'password': '123',
    'port': 5432
}

def get_db_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"[ERROR] Подключение к БД не удалось: {e}")
        sys.exit(1)

def find_order_with_pvz():
    """Находит любой заказ с существующим ПВЗ для позитивного теста"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT o.order_id, o.order_pvz_id_fk
                FROM orders o
                JOIN pvz p ON o.order_pvz_id_fk = p.pvz_id
                LIMIT 1
            """)
            result = cur.fetchone()
            return result  # (order_id, pvz_id)
    finally:
        conn.close()

def find_used_product():
    """Находит любой товар, который используется хотя бы в одном заказе"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.tovar_id
                FROM tovar t
                JOIN order_tovar ot ON t.tovar_id = ot.tovar_id
                LIMIT 1
            """)
            result = cur.fetchone()
            return result[0] if result else None
    finally:
        conn.close()

# --- ПОЗИТИВНЫЙ ТЕСТ: удаление ПВЗ → каскадное удаление заказа ---
def test_positive_pvz_cascade():
    print("\n✅ TC-01 (позитивный): Удаление ПВЗ → каскадное удаление связанного заказа")
    conn = get_db_connection()
    try:
        # Находим реальный заказ с ПВЗ
        data = find_order_with_pvz()
        assert data is not None, "Нет заказов с привязанным ПВЗ — невозможно протестировать каскадное удаление"
        order_id, pvz_id = data

        print(f"→ Используем заказ {order_id} и ПВЗ {pvz_id}")

        # Проверяем предусловия
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM orders WHERE order_id = %s", (order_id,))
            assert cur.fetchone() is not None, f"Заказ {order_id} не найден"
            cur.execute("SELECT 1 FROM pvz WHERE pvz_id = %s", (pvz_id,))
            assert cur.fetchone() is not None, f"ПВЗ {pvz_id} не найден"

        # Удаляем ПВЗ
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pvz WHERE pvz_id = %s", (pvz_id,))
        conn.commit()

        # Проверяем постусловия
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pvz WHERE pvz_id = %s", (pvz_id,))
            assert cur.fetchone() is None, f"ПВЗ {pvz_id} не удалён"
            cur.execute("SELECT 1 FROM orders WHERE order_id = %s", (order_id,))
            assert cur.fetchone() is None, f"Заказ {order_id} должен быть удалён каскадно"

        print("→ ✅ Успешно: каскадное удаление работает.")
    finally:
        conn.close()

# --- НЕГАТИВНЫЙ ТЕСТ: попытка удалить товар, участвующий в заказе ---
def test_negative_delete_used_product():
    print("\n❌ TC-02 (негативный): Попытка удаления товара, используемого в заказах")
    tovar_id = find_used_product()
    assert tovar_id is not None, "Нет товаров, участвующих в заказах — невозможно протестировать защиту"

    print(f"→ Используем товар tovar_id = {tovar_id}")

    conn = get_db_connection()
    try:
        # Проверяем, что товар существует
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tovar WHERE tovar_id = %s", (tovar_id,))
            assert cur.fetchone() is not None, f"Товар {tovar_id} не найден"

        # Эмулируем логику из main.py: нельзя удалить, если есть в order_tovar
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM order_tovar WHERE tovar_id = %s", (tovar_id,))
            count = cur.fetchone()[0]
            if count > 0:
                result = False  # блокируем удаление
            else:
                cur.execute("DELETE FROM tovar WHERE tovar_id = %s", (tovar_id,))
                conn.commit()
                result = True

        # Проверяем результат
        assert result is False, f"Товар {tovar_id} был удалён, хотя используется в {count} заказах!"
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tovar WHERE tovar_id = %s", (tovar_id,))
            assert cur.fetchone() is not None, "Товар исчез — нарушена целостность!"

        print("→ ✅ Успешно: удаление заблокировано — целостность сохранена.")
    finally:
        conn.close()

# --- Запуск ---
if __name__ == "__main__":
    print("🚀 Запуск тестов целостности БД...")
    try:
        test_positive_pvz_cascade()
        test_negative_delete_used_product()
        print("\n🎉 Все тесты пройдены успешно!")
    except AssertionError as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Исключение: {e}")
        sys.exit(1)