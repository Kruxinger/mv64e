import logging
import os
import psycopg2
import json


def get_connection():
    url = os.getenv("DATA_SERVER_URL")
    user = os.getenv("DATA_SERVER_USER")
    password = os.getenv("DATA_SERVER_PASSWORD")

    # URL parsen: jdbc:postgresql://host:port/dbname -> host, port, dbname
    if not url.startswith("jdbc:postgresql://"):
        raise ValueError("Ungültige DATA_SERVER_URL")
    url_parts = url[len("jdbc:postgresql://"):].split("/")
    host_port = url_parts[0].split(":")
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 5432
    dbname = url_parts[1]

    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)

def get_fallnummern(pat_id: str) -> list[int]:

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT fallnummer
                    FROM genomseq_mapping
                    WHERE patienten_id = %s
                    ORDER BY fallnummer
                """, (pat_id,))
                rows = cur.fetchall()
                return [r[0] for r in rows]
    finally:
        conn.close()



def upsert_consent(mv_consent: dict, broad_consent: dict | list, pat_id: str, fallnummer):
    # Fallnummer prüfen
    try:
        fallnummer_int = int(fallnummer)
    except ValueError:
        print(f"Fehler: fallnummer '{fallnummer}' ist nicht konvertierbar zu int")
        return

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Prüfen, ob Zeile existiert
                cur.execute("""
                    SELECT 1 FROM genomseq_mapping 
                    WHERE fallnummer = %s AND patienten_id = %s
                """, (fallnummer_int, pat_id))

                exists = cur.fetchone() is not None

                if exists:
                    # Update
                    cur.execute("""
                        UPDATE genomseq_mapping
                        SET mv_consent = %s, broad_consent = %s
                        WHERE fallnummer = %s AND patienten_id = %s
                    """, (json.dumps(mv_consent), json.dumps(broad_consent), fallnummer_int, pat_id))
                    print("Zeile aktualisiert.")
                else:
                    # Insert
                    cur.execute("""
                        INSERT INTO genomseq_mapping 
                        (fallnummer, patient_id, patienten_id, mv_consent, broad_consent, timestamp)
                        VALUES (%s, %s, %s, %s, %s, now())
                    """, (fallnummer_int, -1, pat_id, json.dumps(mv_consent), json.dumps(broad_consent)))
                    print("Neue Zeile angelegt.")
    finally:
        conn.close()
