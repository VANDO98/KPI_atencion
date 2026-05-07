import sqlite3
import pandas as pd
import os
import re
import unicodedata

DB_NAME = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "logistica_kpi.db"))

def limpiar_texto(texto: str) -> str:
    """Limpia el texto quitando acentos, mayúsculas y espacios extra."""
    if not isinstance(texto, str):
        return ""
    texto = texto.strip().lower()
    # Quitar acentos
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    # Reemplazar múltiples espacios por uno
    texto = re.sub(r'\s+', ' ', texto)
    return texto

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
            Costo REAL DEFAULT 0,
            Valor REAL DEFAULT 0,
            Fecha_Registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ID_Orden, Item)
        )
    """)
    
    # [NUEVO] Migración: Añadir columnas Costo, Valor y Forzado si no existen
    try:
        cursor.execute("ALTER TABLE requerimientos_originales ADD COLUMN Costo REAL DEFAULT 0")
        cursor.execute("ALTER TABLE requerimientos_originales ADD COLUMN Valor REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Ya existen

    try:
        cursor.execute("ALTER TABLE requerimientos_originales ADD COLUMN Forzado INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Ya existe
    
    # 2. Crear tabla despachos_reales [NUEVO]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS despachos_reales (
            ID_Movimiento INTEGER NOT NULL,
            ID_Orden_Ref INTEGER NOT NULL,
            Item TEXT NOT NULL,
            Cantidad_Entregada REAL NOT NULL,
            Fecha_Movimiento TEXT,
            Fecha_Registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            Costo REAL DEFAULT 0,
            Valor REAL DEFAULT 0,
            PRIMARY KEY (ID_Movimiento, Item),
            FOREIGN KEY (ID_Orden_Ref) REFERENCES requerimientos_originales(ID_Orden)
        )
    """)
    
    # [NUEVO] Migración: Añadir columnas Costo y Valor a despachos_reales si no existen
    try:
        cursor.execute("ALTER TABLE despachos_reales ADD COLUMN Costo REAL DEFAULT 0")
        cursor.execute("ALTER TABLE despachos_reales ADD COLUMN Valor REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Ya existen
    
    # 3. Crear Vista KPI [NUEVO]
    # Se agrupa despachos_reales por ID_Orden_Ref e Item para manejar entregas parciales
    cursor.execute("DROP VIEW IF EXISTS v_kpi_fill_rate")
    cursor.execute("""
        CREATE VIEW v_kpi_fill_rate AS
        SELECT 
            r.ID_Orden,
            r.Item,
            m.Unidad,
            r.Almacen_Destino,
            r.Semana,
            r.Tipo_Requerimiento,
            r.Cantidad_Solicitada,
            r.Forzado,
            -- Usar costo del despacho exacto; si no existe, usar precio histórico global del ítem
            COALESCE(d.Costo_Promedio, precio_global.Costo_Global, 0) AS Costo,
            (r.Cantidad_Solicitada * COALESCE(d.Costo_Promedio, precio_global.Costo_Global, 0)) AS Valor,
            CASE 
                WHEN r.Forzado = 1 THEN r.Cantidad_Solicitada 
                ELSE COALESCE(d.Cantidad_Entregada, 0) 
            END AS Cantidad_Entregada,
            CASE 
                WHEN r.Forzado = 1 THEN 0 
                ELSE (r.Cantidad_Solicitada - COALESCE(d.Cantidad_Entregada, 0)) 
            END AS Cantidad_Pendiente,
            CASE 
                WHEN r.Cantidad_Solicitada = 0 THEN 0
                WHEN r.Forzado = 1 THEN 100
                ELSE (COALESCE(d.Cantidad_Entregada, 0) / r.Cantidad_Solicitada) * 100 
            END AS Fill_Rate_Porcentaje
        FROM requerimientos_originales r
        -- Maestro de insumos para la Unidad de Medida
        LEFT JOIN maestro_insumos m ON r.Item = m.Item
        -- Despacho exacto (esta orden + este ítem)
        LEFT JOIN (
            SELECT ID_Orden_Ref, Item, SUM(Cantidad_Entregada) AS Cantidad_Entregada,
                   AVG(CASE WHEN Costo > 0 THEN Costo END) AS Costo_Promedio
            FROM despachos_reales
            GROUP BY ID_Orden_Ref, Item
        ) d ON r.ID_Orden = d.ID_Orden_Ref AND r.Item = d.Item
        -- Precio histórico global del ítem (cualquier orden anterior donde fue despachado con precio)
        LEFT JOIN (
            SELECT Item, AVG(CASE WHEN Costo > 0 THEN Costo END) AS Costo_Global
            FROM despachos_reales
            GROUP BY Item
        ) precio_global ON r.Item = precio_global.Item
    """)
    
    # 4. Crear tabla maestro_insumos [NUEVO]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maestro_insumos (
            Item TEXT PRIMARY KEY,
            Item_Limpio TEXT NOT NULL,
            Categoria TEXT NOT NULL,
            Unidad TEXT,
            Tipo TEXT
        )
    """)
    # 5. Crear tabla correcciones_movimientos [CORREGIDO]
    # Se añade Item_Original para que la corrección sea específica y no por todo el movimiento.
    cursor.execute("DROP TABLE IF EXISTS correcciones_movimientos")
    cursor.execute("""
        CREATE TABLE correcciones_movimientos (
            ID_Movimiento INTEGER,
            Item_Original TEXT,
            Item_Corregido TEXT NOT NULL,
            PRIMARY KEY (ID_Movimiento, Item_Original)
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
            'Cantidad_Solicitada', 'Semana', 'Tipo_Requerimiento', 'Fila_Original',
            'Costo', 'Valor'
        ]
        
        df_insert = df[columnas]
        datos = df_insert.values.tolist()
        
        # [NUEVO] Borrar registros anteriores para sobreescritura completa
        ordenes = df['ID_Orden'].unique().tolist()
        for ord_id in ordenes:
            cursor.execute("DELETE FROM requerimientos_originales WHERE ID_Orden = ?", (int(ord_id),))
            
        query = """
            INSERT OR REPLACE INTO requerimientos_originales 
            (ID_Orden, Item, Almacen_Destino, Presentacion, Cantidad_Solicitada, Semana, Tipo_Requerimiento, Fila_Original, Costo, Valor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        
        # [CORREGIDO] Aplicar correcciones manuales específicas (ID_Movimiento + Item_Original)
        cursor.execute("SELECT ID_Movimiento, Item_Original, Item_Corregido FROM correcciones_movimientos")
        # Diccionario anidado: { id_mov: { item_orig: item_corr } }
        correcciones = {}
        for mid, orig, corr in cursor.fetchall():
            if mid not in correcciones:
                correcciones[mid] = {}
            correcciones[mid][orig] = corr
            
        if correcciones:
            def aplicar_corr(row):
                mid = int(row['ID_Movimiento']) if pd.notna(row.get('ID_Movimiento')) else None
                item = row['Item']
                if mid in correcciones and item in correcciones[mid]:
                    return correcciones[mid][item]
                return item
                
            df['Item'] = df.apply(aplicar_corr, axis=1)

        columnas = ['ID_Movimiento', 'ID_Orden_Ref', 'Item', 'Cantidad_Entregada', 'Fecha_Movimiento', 'Costo', 'Valor']
        df_insert = df[columnas]
        datos = df_insert.values.tolist()
        
        # [NUEVO] Borrar registros anteriores para sobreescritura completa
        movimientos = df['ID_Movimiento'].unique().tolist()
        for mov_id in movimientos:
            cursor.execute("DELETE FROM despachos_reales WHERE ID_Movimiento = ?", (int(mov_id),))
            
        query = """
            INSERT OR REPLACE INTO despachos_reales 
            (ID_Movimiento, ID_Orden_Ref, Item, Cantidad_Entregada, Fecha_Movimiento, Costo, Valor)
            VALUES (?, ?, ?, ?, ?, ?, ?)
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

def eliminar_orden(id_orden: int) -> int:
    """Elimina una orden completa de requerimientos_originales."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM requerimientos_originales WHERE ID_Orden = ?", (id_orden,))
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def cargar_maestro_insumos(df: pd.DataFrame) -> int:
    """
    Carga el maestro de insumos desde un DataFrame.
    """
    if df.empty:
        return 0
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Limpiar tabla
        cursor.execute("DELETE FROM maestro_insumos")
        
        data_to_insert = []
        for _, row in df.iterrows():
            item_original = str(row.get('Nombre', '')).strip()
            item_limpio = limpiar_texto(item_original)
            categoria = str(row.get('Categoría', 'Sin Categoría')).strip()
            unidad = str(row.get('Unidad', '')).strip() if 'Unidad' in df.columns else None
            tipo = str(row.get('Tipo', '')).strip() if 'Tipo' in df.columns else None
            
            if item_original and item_original != 'nan':
                data_to_insert.append((item_original, item_limpio, categoria, unidad, tipo))
                
        query = """
            INSERT OR REPLACE INTO maestro_insumos (Item, Item_Limpio, Categoria, Unidad, Tipo)
            VALUES (?, ?, ?, ?, ?)
        """
        cursor.executemany(query, data_to_insert)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def obtener_maestro_insumos():
    """Retorna el maestro de insumos como DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM maestro_insumos", conn)
    conn.close()
    return df

def corregir_item_despacho(id_movimiento: int, item_original: str, item_nuevo: str) -> int:
    """
    Actualiza el nombre del ítem en la tabla despachos_reales para un movimiento específico.
    Esto permite vincular un ítem con error de tipeo al ítem original de la orden.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE despachos_reales SET Item = ? WHERE ID_Movimiento = ? AND Item = ?",
            (item_nuevo, id_movimiento, item_original)
        )
        
        # [CORREGIDO] Guardar en la tabla de correcciones con el ítem original como parte de la clave
        cursor.execute(
            "INSERT OR REPLACE INTO correcciones_movimientos (ID_Movimiento, Item_Original, Item_Corregido) VALUES (?, ?, ?)",
            (id_movimiento, item_original, item_nuevo)
        )
        
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def forzar_cumplimiento(id_orden: int, item: str) -> int:
    """
    Marca un ítem específico de una orden como 'Forzado' (=1),
    lo cual indica que la Cantidad Entregada se igualará matemáticamente a la Solicitada.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE requerimientos_originales SET Forzado = 1 WHERE ID_Orden = ? AND Item = ?",
            (id_orden, item)
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
