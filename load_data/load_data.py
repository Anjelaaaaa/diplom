import pymysql
import pandas as pd
from datetime import datetime
import numpy as np

def load_excel_with_scha_fixed():
    """Загрузка данных с исправлением проблемы scha"""
    
    print("📁 ЗАГРУЗКА ДАННЫХ ИЗ EXCEL (ИСПРАВЛЕННАЯ)")
    print("=" * 60)
    
    # 1. Читаем Excel файл
    try:
        df = pd.read_excel('charts.xlsx', sheet_name='Ark1')
        
        print(f"✅ Прочитано {len(df)} строк")
        print("📋 Колонки:", df.columns.tolist())
        
        # Показываем информацию о типах данных
        print("\n🔍 Типы данных в колонках:")
        for col in df.columns:
            dtype = df[col].dtype
            non_null = df[col].notna().sum()
            print(f"  {col}: {dtype} ({non_null} не пустых)")
        
        # Особенно смотрим на scha
        print("\n🔍 Детальная информация о scha:")
        scha_sample = df['scha'].head(5)
        for i, val in enumerate(scha_sample, 1):
            print(f"  Строка {i}: {val} (тип: {type(val).__name__})")
        
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return
    
    # 2. Подключаемся к MySQL
    conn = pymysql.connect(
        host='localhost',
        user='recordcapital',
        password='715302',
        database='recordcapital',
        charset='utf8mb4'
    )
    
    try:
        with conn.cursor() as cursor:
            # 3. Очищаем старые данные
            cursor.execute("DELETE FROM fund_values WHERE fund_id = 1")
            deleted = cursor.rowcount
            print(f"\n🗑️  Удалено старых записей: {deleted}")
            
            # 4. Загружаем данные
            print("\n🔄 Загрузка данных...")
            loaded_count = 0
            error_count = 0
            
            for index, row in df.iterrows():
                try:
                    # Пропускаем пустые строки
                    if pd.isna(row['date']) or pd.isna(row['share_price']):
                        continue
                    
                    # Преобразуем данные
                    fund_id = 1
                    
                    # Дата
                    date_obj = row['date']
                    if isinstance(date_obj, (datetime, pd.Timestamp)):
                        date = date_obj.date()
                    else:
                        # Если строка, конвертируем
                        date_str = str(date_obj).split()[0]
                        if '-' in date_str:
                            date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        else:
                            date = datetime.strptime(date_str, '%d.%m.%Y').date()
                    
                    # Цена акции
                    share_price = float(row['share_price'])
                    
                    # Benchmark
                    benchmark = None
                    if 'benchmark' in df.columns and pd.notna(row['benchmark']):
                        benchmark_val = row['benchmark']
                        if isinstance(benchmark_val, (int, float, np.integer, np.floating)):
                            benchmark = float(benchmark_val)
                        elif isinstance(benchmark_val, str):
                            benchmark = float(benchmark_val.replace(',', '.'))
                    
                    # SCHA - ОСОБОЕ ВНИМАНИЕ!
                    scha = None
                    if 'scha' in df.columns:
                        scha_val = row['scha']
                        
                        if pd.notna(scha_val):
                            # Пробуем разные способы преобразования
                            try:
                                if isinstance(scha_val, (int, float, np.integer, np.floating)):
                                    scha = float(scha_val)
                                elif isinstance(scha_val, str):
                                    # Убираем пробелы и заменяем запятую
                                    scha_clean = scha_val.strip().replace(' ', '').replace(',', '.')
                                    scha = float(scha_clean)
                                else:
                                    # Пробуем преобразовать в строку и потом в float
                                    scha = float(str(scha_val).replace(',', '.'))
                            except Exception as e:
                                print(f"⚠️  Ошибка преобразования scha в строке {index+2}: {scha_val} -> {e}")
                                scha = None
                    
                    # Вставляем в базу
                    sql = """
                    INSERT INTO fund_values (fund_id, date, share_price, benchmark, scha, upload_date)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    """
                    
                    cursor.execute(sql, (fund_id, date, share_price, benchmark, scha))
                    loaded_count += 1
                    
                    # Показываем прогресс
                    if loaded_count % 500 == 0:
                        print(f"  ↳ Загружено: {loaded_count} записей")
                        
                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        print(f"⚠️  Ошибка в строке {index+2}: {e}")
                    continue
            
            # Сохраняем изменения
            conn.commit()
            
            print(f"\n" + "=" * 50)
            print("✅ РЕЗУЛЬТАТЫ ЗАГРУЗКИ:")
            print(f"   Успешно загружено: {loaded_count} записей")
            print(f"   Ошибок обработки: {error_count}")
            
            # 5. Проверяем результат
            cursor.execute("SELECT COUNT(*) FROM fund_values WHERE fund_id = 1")
            total_in_db = cursor.fetchone()[0]
            print(f"   Всего в базе (fund_id=1): {total_in_db}")
            
            if total_in_db > 0:
                # Статистика
                cursor.execute("""
                    SELECT 
                        COUNT(CASE WHEN scha IS NOT NULL THEN 1 END) as scha_count,
                        COUNT(*) as total,
                        ROUND(COUNT(CASE WHEN scha IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) as scha_percent,
                        MIN(scha) as min_scha,
                        MAX(scha) as max_scha
                    FROM fund_values 
                    WHERE fund_id = 1
                """)
                
                stats = cursor.fetchone()
                print(f"\n📊 Статистика по SCHA:")
                print(f"   Записей с SCHA: {stats[0]}/{stats[1]} ({stats[2]}%)")
                print(f"   Минимальное SCHA: {stats[3]:,.2f}" if stats[3] else "   Минимальное SCHA: N/A")
                print(f"   Максимальное SCHA: {stats[4]:,.2f}" if stats[4] else "   Максимальное SCHA: N/A")
                
                # Показываем примеры записей с SCHA
                cursor.execute("""
                    SELECT date, share_price, benchmark, scha
                    FROM fund_values 
                    WHERE fund_id = 1 
                    AND scha IS NOT NULL
                    ORDER BY date 
                    LIMIT 5
                """)
                
                scha_records = cursor.fetchall()
                if scha_records:
                    print(f"\n📅 Примеры записей с SCHA:")
                    for date, price, bench, scha in scha_records:
                        print(f"   {date}: цена={price:.2f}, benchmark={bench or 'N/A'}, scha={scha}")
                else:
                    print(f"\n❌ Нет записей с SCHA!")
                    
                    # Проверяем почему
                    print("\n🔍 Проверяем данные в Excel...")
                    scha_in_excel = df['scha'].notna().sum()
                    print(f"   В Excel есть {scha_in_excel} непустых значений SCHA")
                    
                    if scha_in_excel > 0:
                        print("   Примеры значений SCHA из Excel:")
                        for i in range(min(5, len(df))):
                            if pd.notna(df.iloc[i]['scha']):
                                print(f"   Строка {i+1}: {df.iloc[i]['scha']}")
                
                # Общая статистика
                cursor.execute("""
                    SELECT 
                        MIN(date) as first_date,
                        MAX(date) as last_date,
                        COUNT(*) as total,
                        ROUND(MIN(share_price), 2) as min_price,
                        ROUND(MAX(share_price), 2) as max_price,
                        ROUND(AVG(share_price), 2) as avg_price
                    FROM fund_values 
                    WHERE fund_id = 1
                """)
                
                stats = cursor.fetchone()
                print(f"\n📊 Общая статистика:")
                print(f"   Первая дата: {stats[0]}")
                print(f"   Последняя дата: {stats[1]}")
                print(f"   Всего записей: {stats[2]}")
                print(f"   Минимальная цена: {stats[3]:.2f}")
                print(f"   Максимальная цена: {stats[4]:.2f}")
                print(f"   Средняя цена: {stats[5]:.2f}")
                
            print("=" * 50)
            
    except Exception as e:
        print(f"❌ Ошибка MySQL: {e}")
        conn.rollback()
    finally:
        conn.close()

# Запустите эту функцию
load_excel_with_scha_fixed()