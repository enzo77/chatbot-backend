import sqlite3

conn = sqlite3.connect("chatbot.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("\n=== TABLAS ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
print([row[0] for row in cursor.fetchall()])

print("\n=== CONVERSACIONES ===")
cursor.execute("SELECT * FROM conversaciones")
convs = cursor.fetchall()
if convs:
    for conv in convs:
        print(f"  ID: {conv['id']} | Creada: {conv['created']}")
else:
    print("  (vacía)")

print("\n=== MENSAJES ===")
cursor.execute("SELECT * FROM mensajes ORDER BY id")
mensajes = cursor.fetchall()
if mensajes:
    for msg in mensajes:
        print(f"  [{msg['id']}] {msg['role'].upper()} ({msg['conversation_id'][:8]}...)")
        print(f"       {msg['content'][:80]}...")
else:
    print("  (vacía)")

conn.close()
