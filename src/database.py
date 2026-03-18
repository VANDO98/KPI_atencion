import sqlite3
import pandas as pd
import os

DB_NAME = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "logistica_kpi.db"))

def get_connection():
    """Retorna una conexión a la base de datos SQLite."""
    return sqlite3.connect(DB_NAME)

def init_db():
    """Inicializa la base de datos y crea las tablas y vistas si no existen."""
    # Asegurar que existan las carpetas data/ y data/ordenes/
    db_dir = os.path.dirname(DB_NAME)
    ordenes_dir = os.path.join(db_dir, "ordenes")
    
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    if not os.path.exists(ordenes_dir):
        os.makedirs(ordenes_dir)

    conn = get_connection()
    cursor = conn.cursor()
    
    # Activar Foreign Keys (Opcional pero recomendado)
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # 1. Crear tabla requerimientos_originales
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requerimientos_originales (
            ID_Orden INTEGER NOT NULL,
            Item TEXT NOT NULL,
            Almacen_Destino TEXT NOT NULL,
            Presentacion TEXT NOT NULL,
            Cantidad_Solicitada REAL NOT NULL,
            Semana TEXT NOT NULL,
            Tipo_Requerimiento TEXT NOT NULL,
            Fila_Original INTEGER,
            Fecha_Registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ID_Orden, Item)
        )
    """)
    
    # 2. Crear tabla despachos_reales [NUEVO]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS despachos_reales (
            ID_Movimiento INTEGER NOT NULL,
            ID_Orden_Ref INTEGER NOT NULL,
            Item TEXT NOT NULL,
            Cantidad_Entregada REAL NOT NULL,
            Fecha_Movimiento TEXT,
            Fecha_Registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ID_Movimiento, Item),
            FOREIGN KEY (ID_Orden_Ref) REFERENCES requerimientos_originales(ID_Orden)
        )
    """)
    
    # 3. Crear Vista KPI [NUEVO]
    # Se agrupa despachos_reales por ID_Orden_Ref e Item para manejar entregas parciales
    cursor.execute("""
        CREATE VIEW IF NOT EXISTS v_kpi_fill_rate AS
        SELECT 
            r.ID_Orden,
            r.Item,
            r.Almacen_Destino,
            r.Semana,
            r.Tipo_Requerimiento,
            r.Cantidad_Solicitada,
            COALESCE(d.Cantidad_Entregada, 0) AS Cantidad_Entregada,
            (r.Cantidad_Solicitada - COALESCE(d.Cantidad_Entregada, 0)) AS Cantidad_Pendiente,
            CASE 
                WHEN r.Cantidad_Solicitada = 0 THEN 0
                ELSE (COALESCE(d.Cantidad_Entregada, 0) / r.Cantidad_Solicitada) * 100 
            END AS Fill_Rate_Porcentaje
        FROM requerimientos_originales r
        LEFT JOIN (
            SELECT ID_Orden_Ref, Item, SUM(Cantidad_Entregada) AS Cantidad_Entregada
            FROM despachos_reales
            GROUP BY ID_Orden_Ref, Item
        ) d ON r.ID_Orden = d.ID_Orden_Ref AND r.Item = d.Item
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
        
        # [NUEVO] Borrar registros anteriores para sobreescritura completa
        ordenes = df['ID_Orden'].unique().tolist()
        for ord_id in ordenes:
            cursor.execute("DELETE FROM requerimientos_originales WHERE ID_Orden = ?", (int(ord_id),))
            
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

def insertar_despachos(df: pd.DataFrame):
    """
    Inserta o reemplaza registros en la tabla despachos_reales.
    """
    if df.empty:
        return 0
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        columnas = ['ID_Movimiento', 'ID_Orden_Ref', 'Item', 'Cantidad_Entregada', 'Fecha_Movimiento']
        df_insert = df[columnas]
        datos = df_insert.values.tolist()
        
        # [NUEVO] Borrar registros anteriores para sobreescritura completa
        movimientos = df['ID_Movimiento'].unique().tolist()
        for mov_id in movimientos:
            cursor.execute("DELETE FROM despachos_reales WHERE ID_Movimiento = ?", (int(mov_id),))
            
        query = """
            INSERT OR REPLACE INTO despachos_reales 
            (ID_Movimiento, ID_Orden_Ref, Item, Cantidad_Entregada, Fecha_Movimiento)
            VALUES (?, ?, ?, ?, ?)
        """
        
        cursor.executemany(query, datos)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def obtener_reporte_kpi(semana=None, almacen=None, tipo=None):
    """
    Consulta la vista v_kpi_fill_rate aplicando filtros opcionales.
    """
    query = "SELECT * FROM v_kpi_fill_rate WHERE 1=1"
    params = []
    
    if semana:
        query += " AND Semana = ?"
        params.append(semana)
    if almacen:
        query += " AND Almacen_Destino = ?"
        params.append(almacen)
    if tipo:
        query += " AND Tipo_Requerimiento = ?"
        params.append(tipo)
        
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def obtener_historial_despachos():
    """
    Retorna el historial de despachos cargados.
    """
    query = """
        SELECT DISTINCT ID_Movimiento, ID_Orden_Ref, Fecha_Movimiento, Fecha_Registro
        FROM despachos_reales
        ORDER BY ID_Movimiento DESC
    """
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def actualizar_tipo_orden(id_orden: int, nuevo_tipo: str) -> int:
    """
    Actualiza el Tipo_Requerimiento para todos los registros de una ID_Orden.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE requerimientos_originales SET Tipo_Requerimiento = ? WHERE ID_Orden = ?",
            (nuevo_tipo, id_orden)
        )
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def obtener_lista_ordenes():
    """
    Retorna la lista de órdenes únicas con su semana y tipo.
    """
    query = """
        SELECT ID_Orden, Semana, Tipo_Requerimiento 
        FROM requerimientos_originales
        GROUP BY ID_Orden
    """
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def actualizar_orden(id_orden: int, semana: str, tipo: str) -> int:
    """
    Actualiza la semana y el tipo de requerimiento para todos los registros de una ID_Orden.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE requerimientos_originales SET Semana = ?, Tipo_Requerimiento = ? WHERE ID_Orden = ?",
            (semana, tipo, id_orden)
        )
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    # Inicializar si se corre directo
    init_db()
    print("Base de datos inicializada correctamente.")
