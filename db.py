import sqlite3
import os

# 資料庫文件
DB_PATH = "example.db"

# 顯示資料庫檔案路徑
print(f"資料庫路徑: {os.path.abspath(DB_PATH)}")

# 初始化資料庫表格，確保 `user_id` 和 `info` 欄位存在
def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # 僅在表格不存在的情況下創建
        c.execute("""
            CREATE TABLE IF NOT EXISTS BackgroundInfo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                info TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        print("資料庫初始化完成。")

    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}")

# 新增背景資訊
def add_background_info(user_id, new_info):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        print(f"插入資料: user_id = {user_id}, info = {new_info}")
        c.execute("""
            INSERT INTO BackgroundInfo (user_id, info) VALUES (?, ?)
        """, (user_id, new_info))

        conn.commit()
        print("資料已成功寫入資料庫。")
        conn.close()

    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}")
    except Exception as e:
        print(f"未知錯誤: {e}")

# 批量新增背景資訊
def add_bulk_background_info(user_id, info_list):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        print(f"批量插入資料: user_id = {user_id}")
        c.executemany("""
            INSERT INTO BackgroundInfo (user_id, info) VALUES (?, ?)
        """, [(user_id, info) for info in info_list])

        conn.commit()
        print("批量資料已成功寫入資料庫。")
        conn.close()

    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}")
    except Exception as e:
        print(f"未知錯誤: {e}")

# 查詢所有背景資訊
def get_all_background_info():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        print("查詢資料...")
        c.execute("""SELECT id, user_id, info FROM BackgroundInfo""")
        rows = c.fetchall()

        if not rows:
            print("目前資料庫中沒有任何背景資訊。")
        else:
            for row in rows:
                print(f"ID: {row[0]}, 使用者ID: {row[1]}, 背景資訊: {row[2]}")

        conn.close()

    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}")
    except Exception as e:
        print(f"未知錯誤: {e}")

# 刪除指定 ID 的資料
def delete_background_info_by_id(record_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        print(f"刪除資料 ID: {record_id}")
        c.execute("DELETE FROM BackgroundInfo WHERE id = ?", (record_id,))
        conn.commit()

        if c.rowcount > 0:
            print("資料已成功刪除。")
        else:
            print("未找到指定 ID 的資料。")

        conn.close()

    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}")
    except Exception as e:
        print(f"未知錯誤: {e}")

# 批量刪除指定 ID 的資料
def delete_bulk_background_info(record_ids):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        print(f"批量刪除資料 ID: {record_ids}")
        placeholders = ",".join(["?"] * len(record_ids))  # 動態生成占位符
        query = f"DELETE FROM BackgroundInfo WHERE id IN ({placeholders})"
        c.execute(query, record_ids)
        conn.commit()

        if c.rowcount > 0:
            print(f"已成功刪除 {c.rowcount} 筆資料。")
        else:
            print("未找到指定 ID 的資料。")

        conn.close()

    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}")
    except Exception as e:
        print(f"未知錯誤: {e}")

# 主程式
if __name__ == "__main__":
    init_db()

    print("1. 新增背景資訊")
    print("2. 查看所有背景資訊")
    print("3. 批量新增背景資訊")
    print("4. 刪除指定 ID 的資料")
    print("5. 批量刪除指定 ID 的資料")

    choice = input("請選擇操作 (1/2/3/4/5): ").strip()

    if choice == "1":
        user_id = input("請輸入使用者ID: ").strip()
        new_info = input("請輸入新的背景資訊: ").strip()
        add_background_info(user_id, new_info)
    elif choice == "2":
        get_all_background_info()
    elif choice == "3":
        user_id = input("請輸入使用者ID: ").strip()
        print("請輸入多條背景資訊（每條資訊一行）：")
        info_list = []
        while True:
            new_info = input("背景資訊 (按 Enter 結束輸入): ").strip()
            if not new_info:
                break
            info_list.append(new_info)
        add_bulk_background_info(user_id, info_list)
    elif choice == "4":
        record_id = input("請輸入要刪除的資料 ID: ").strip()
        if record_id.isdigit():
            delete_background_info_by_id(int(record_id))
        else:
            print("無效的 ID，請輸入數字。")
    elif choice == "5":
        print("請輸入要批量刪除的資料 ID，用逗號分隔（例如: 1,2,3）")
        record_ids = input("請輸入 ID 列表: ").strip()
        try:
            id_list = [int(id.strip()) for id in record_ids.split(",") if id.strip().isdigit()]
            if id_list:
                delete_bulk_background_info(id_list)
            else:
                print("無效的輸入，請輸入有效的數字 ID。")
        except ValueError:
            print("無效的輸入，請確認格式正確。")
    else:
        print("無效選擇")
