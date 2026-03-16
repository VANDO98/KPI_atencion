import sqlite3
import pandas as pd
import os

DB_NAME = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "logistica_kpi.db"))

def get_connection():
    """Retorna una conexión a la base de datos SQLite."""
    return sqlite3.connect(DB_NAME)

def init_db():
    """Inicializa la base de datos y crea la tabla si no existe."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Crear tabla requerimientos_originales
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requerimientos_originales (
            ID_Orden INTEGER NOT NULL,
            Item TEXT NOT NULL,
            Almacen_Destino TEXT NOT NULL,
            Presentacion TEXT NOT NULL,
            Cantidad_Solicitada REAL NOT NULL,
            Semana TEXT NOT NULL,
            Tipo_Requerimiento TEXT NOT NULL,
            Fila_Original INTEGER, -- Columna para preservar orden
            Fecha_Registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ID_Orden, Item)
        )
    """)
    conn.commit()
    conn.close()

def insertar_requerimientos(df: pd.DataFrame):
    """
    Inserta o reemplaza registros en la tabla requerimientos_originales.
    """
    if df.empty:
        return 0
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        columnas = [
            'ID_Orden', 'Item', 'Almacen_Destino', 'Presentacion', 
            'Cantidad_Solicitada', 'Semana', 'Tipo_Requerimiento', 'Fila_Original'
        ]
        
        df_insert = df[columnas]
        datos = df_insert.values.tolist()
        
        query = """
            INSERT OR REPLACE INTO requerimientos_originales 
            (ID_Orden, Item, Almacen_Destino, Presentacion, Cantidad_Solicitada, Semana, Tipo_Requerimiento, Fila_Original)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        cursor.executemany(query, datos)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def obtener_historial():
    """
    Retorna el historial de órdenes agrupado.
    """
    query = """
        SELECT DISTINCT ID_Orden, Almacen_Destino, Semana, Tipo_Requerimiento 
        FROM requerimientos_originales 
        ORDER BY ID_Orden DESC
    """
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def obtener_metricas():
    """
    Retorna métricas rápidas.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT ID_Orden) FROM requerimientos_originales")
    total_ordenes = cursor.fetchone()[0] or 0
    conn.close()
    return {"total_ordenes": total_ordenes}

def obtener_items_por_orden(id_orden):
    """
    Retorna los ítems de una orden respetando el orden original del PDF.
    """
    query = """
        SELECT Item, Presentacion, Cantidad_Solicitada, Semana, Tipo_Requerimiento 
        FROM requerimientos_originales 
        WHERE ID_Orden = ?
        ORDER BY Fila_Original ASC
    """
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=(id_orden,))
    conn.close()
    return df

if __name__ == "__main__":
    # Inicializar si se corre directo
    init_db()
    print("Base de datos inicializada correctamente.")
