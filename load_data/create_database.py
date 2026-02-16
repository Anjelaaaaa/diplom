import pymysql

ROOT_PASSWORD = "fh8#74dg4&h87?dzxhh7"  

try:
    print("🔄 Подключаемся к MySQL как root...")
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password=ROOT_PASSWORD,
        charset='utf8mb4'
    )
    
    with connection.cursor() as cursor:
        print("📁 Создаем базу данных 'recordcapital'...")
        cursor.execute("CREATE DATABASE IF NOT EXISTS recordcapital CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        
        print("👤 Создаем пользователя для Flask приложения...")
        # Создаем пользователя 'recordcapital' с паролем '715302'
        cursor.execute("CREATE USER IF NOT EXISTS 'recordcapital'@'localhost' IDENTIFIED BY '715302';")
        
        print("🔑 Назначаем права...")
        cursor.execute("GRANT ALL PRIVILEGES ON recordcapital.* TO 'recordcapital'@'localhost';")
        cursor.execute("FLUSH PRIVILEGES;")
        
        # Проверяем
        cursor.execute("SHOW DATABASES;")
        databases = cursor.fetchall()
        print("📋 Список баз данных:")
        for db in databases:
            print(f"   - {db[0]}")
    
    connection.commit()
    
    print("\n" + "="*60)
    print("✅ БАЗА ДАННЫХ СОЗДАНА УСПЕШНО!")
    print("="*60)
    print("\nНастройки для вашего Flask приложения:")
    print("-"*60)
    print("app.config['SQLALCHEMY_DATABASE_URI'] =")
    print("'mysql+pymysql://recordcapital:715302@localhost:3306/recordcapital'")
    print("-"*60)
    print("\n⚠️  Не забудьте:")
    print("1. Установить pymysql: pip install pymysql")
    print("2. Обновить конфигурацию Flask")
    print("3. Запустить Flask для создания таблиц")
    
except pymysql.Error as e:
    print(f"\n❌ Ошибка подключения: {e}")
    
    if e.args[0] == 1045:  # Access denied
        print("\n⚠️  Неверный пароль root!")
        print("Используйте пароль, который вы задали при установке MySQL.")
        print("Если забыли пароль, можно:")
        print("1. Переустановить MySQL")
        print("2. Или сбросить пароль root (сложнее)")
    
    elif e.args[0] == 2003:  # Can't connect
        print("\n⚠️  Не могу подключиться к MySQL!")
        print("Проверьте:")
        print("1. Запущена ли служба MySQL80")
        print("2. Порт 3306 открыт")
        print("3. Брандмауэр не блокирует подключение")
    
    print("\nПроверьте службу MySQL:")
    print("1. Нажмите Win + R")
    print("2. Введите services.msc")
    print("3. Найдите 'MySQL80'")
    print("4. Убедитесь что статус 'Выполняется'")
    
except Exception as e:
    print(f"❌ Неожиданная ошибка: {e}")

finally:
    if 'connection' in locals():
        connection.close()
        print("\n🔒 Соединение закрыто")