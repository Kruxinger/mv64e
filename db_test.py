import os
import psycopg2

# Windows / lokale Verbindung: Docker-DB läuft auf localhost
DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_NAME = os.environ.get("POSTGRES_DB", "onco")
DB_USER = os.environ.get("POSTGRES_USER", "onco_user")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "onco_pass")

def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        options='-c client_encoding=UTF8'
    )

def list_tables(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
        return [t[0] for t in cur.fetchall()]

def table_columns(conn, table_name):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name=%s;
        """, (table_name,))
        return cur.fetchall()

def main():
    try:
        conn = get_conn()
        print("✅ Verbindung erfolgreich!")

        tables = list_tables(conn)
        print("\nTabellen in der DB:")
        for t in tables:
            print("-", t)

        # Spalten jeder wichtigen Tabelle prüfen
        for table in ["cases", "constants", "logs", "transmissions"]:
            if table in tables:
                print(f"\nSpalten der Tabelle '{table}':")
                cols = table_columns(conn, table)
                for col in cols:
                    print("  ", col)
            else:
                print(f"\n⚠ Tabelle '{table}' fehlt!")

    except psycopg2.Error as e:
        print("❌ DB-Verbindungsfehler:", e)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
