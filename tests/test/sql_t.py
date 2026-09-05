import psycopg2

conn = psycopg2.connect(
    host="172.18.20.17",
    port=5432,
    user="postgres",
    password="Hello12345*",
    dbname="googlesheet_validator",
    connect_timeout=5,
)
print("connected")
conn.close()
