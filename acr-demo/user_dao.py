# ACR 全链路验证样例(故意包含典型问题)
DB_PASSWORD = "admin123!@#"
DB_USER = "root"

def find_user(cursor, username):
    sql = "SELECT * FROM users WHERE name = '" + username + "'"
    try:
        return cursor.execute(sql)
    except:
        return None
