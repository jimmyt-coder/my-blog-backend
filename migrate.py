
import sqlite3
import psycopg2
import os

# --- 配置区 ---
local_db = os.path.join('instance', 'travel.db')
# 【关键】请填入你的 External Database URL
cloud_url = "postgresql://jimmyt:f879arZftWNujKeT5u2ZvUpZdHj1Wabm@dpg-d5ejb0u3jp1c73deqlsg-a.frankfurt-postgres.render.com/blog_data_2mqc"

def start_migration():
    conn_sqlite = None
    conn_pg = None
    try:
        print("🚚 发现 7 个字段，正在精准搬家...")
        conn_sqlite = sqlite3.connect(local_db)
        cursor_sqlite = conn_sqlite.cursor()

        conn_pg = psycopg2.connect(cloud_url)
        cursor_pg = conn_pg.cursor()

        # 1. 在云端创建完全匹配的表结构
        cursor_pg.execute("""
            CREATE TABLE IF NOT EXISTS post (
                id SERIAL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                image_url VARCHAR(500),
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)

        # 2. 从本地读取这 7 个字段
        cursor_sqlite.execute("SELECT id, title, content, image_url, user_id, created_at, updated_at FROM post")
        posts = cursor_sqlite.fetchall()

        if not posts:
            print("⚠️ 本地数据库没找到文章数据。")
            return

        # 3. 写入云端
        cursor_pg.execute("TRUNCATE TABLE post RESTART IDENTITY") # 清空旧数据并重置ID计数
        for p in posts:
            cursor_pg.execute(
                "INSERT INTO post (id, title, content, image_url, user_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                p
            )
        
        conn_pg.commit()
        print(f"✅ 搬家成功！已同步 {len(posts)} 条数据到 PostgreSQL 保险柜。")

    except Exception as e:
        print(f"❌ 搬家失败，原因: {e}")
    finally:
        if conn_sqlite: conn_sqlite.close()
        if conn_pg: conn_pg.close()

if __name__ == '__main__':
    start_migration()