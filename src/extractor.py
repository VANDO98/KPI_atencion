import pdfplumber
import pandas as pd
import re
import io
import os

def extraer_cabecera(texto_pagina):
    """
    Extrae ID_Orden y Almacen_Destino usando regex.
    """
    id_orden = None
    almacen_destino = None
    
    # regex para ID_Orden
    # Orden de Movimiento #1341
    match_orden = re.search(r"Orden de Movimiento #(\d+)", texto_pagina)
    if match_orden:
        id_orden = int(match_orden.group(1))
        
    # regex para Almacen_Destino
    # Almacén destino: Cocina Materiales
    match_almacen = re.search(r"Almacén destino:\s*(.+)", texto_pagina)
    if match_almacen:
        almacen_destino = match_almacen.group(1).replace('\n', ' ').strip()
        # Colapsar múltiples espacios
        almacen_destino = re.sub(r'\s+', ' ', almacen_destino)
        
    return id_orden, almacen_destino

def limpiar_cantidad(val):
    """
    Limpia y convierte a float una cantidad, removiendo comas, saltos de línea y espacios.
    """
    if pd.isna(val) or val == "":
        return 0.0
    try:
        # Eliminar saltos de línea, comas (miles) y espacios
        val_str = str(val).replace('\n', ' ').replace('\r', '').replace(',', '').strip()
        # Eliminar cualquier caracter no numérico excepto punto y signo negativo
        val_str = re.sub(r'[^\d.\-]', '', val_str)
        if not val_str or val_str == '.':
            return 0.0
        return float(val_str)
    except ValueError:
        return 0.0

def detectar_columnas(df):
    """
    Escanea las primeras filas del DataFrame para detectar los índices de columnas clave.
    Requiere encontrar al menos la columna 'Item' para que la detección sea válida.
    Fallback seguro: Cant=0, Item=1, Presentacion=2, Costo=-1, Valor=-1.
    """
    indices = {"Cant": 0, "Item": 1, "Presentacion": 2, "Costo": -1, "Valor": -1}
    
    for _, row in df.head(10).iterrows():
        # Convertir fila a strings limpios (sin newlines)
        row_str = [str(cell).replace('\n', ' ').lower().strip() for cell in row]
        
        # --- Buscar columna Item como ancla principal ---
        item_keywords = ['item', 'artículo', 'articulo', 'descripción', 'descripcion', 'producto', 'nombre']
        idx_item = -1
        
        # 1. Coincidencia EXACTA
        for kw in item_keywords:
            if kw in row_str:
                idx_item = row_str.index(kw)
                break
        
        # 2. Coincidencia PARCIAL (ej. "nombre de item")
        if idx_item == -1:
            for j, cell in enumerate(row_str):
                if 'item' in cell or 'descripci' in cell or 'producto' in cell:
                    idx_item = j
                    break
                    
        if idx_item == -1:
            continue  # Esta fila no tiene cabecera, seguir buscando
            
        indices["Item"] = idx_item
        
        # --- Buscar Cantidad (primera columna con 'cant' que no sea Item) ---
        for j, cell in enumerate(row_str):
            if 'cant' in cell and j != idx_item:
                indices["Cant"] = j
                break
                
        # --- Buscar Presentación ---
        for j, cell in enumerate(row_str):
            if 'present' in cell and j != idx_item:
                indices["Presentacion"] = j
                break
                
        # --- Buscar Costo ---
        for j, cell in enumerate(row_str):
            if any(kw in cell for kw in ['costo', 'p.u', 'precio', 'unit']) and j not in [idx_item, indices["Cant"]]:
                indices["Costo"] = j
                break
                
        # --- Buscar Valor/Total ---
        for j, cell in enumerate(row_str):
            if any(kw in cell for kw in ['valor', 'total', 'monto', 'importe']) and j not in [idx_item, indices["Cant"], indices["Costo"]]:
                indices["Valor"] = j
                break
                
        return indices  # Retornar con la primera fila válida
        
    return indices  # Fallback si ninguna fila tiene cabecera

def extraer_tabla(pdf):
    """
    Extrae todas las tablas de todas las páginas y las concatena.
    """
    all_rows = []
    
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_rows.extend(table)
            
    if not all_rows:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_rows)
    
    if df.empty:
        return df
        
    # [NUEVO] Detección Dinámica de Columnas
    idx_cols = detectar_columnas(df)
    idx_cant = idx_cols["Cant"]
    idx_item = idx_cols["Item"]
    idx_pres = idx_cols["Presentacion"]
    idx_cost = idx_cols.get("Costo", -1)
    idx_val  = idx_cols.get("Valor", -1)
    
    # Validar que no sean iguales o desbordados
    if idx_cant >= len(df.columns) or idx_item >= len(df.columns) or idx_pres >= len(df.columns):
        # Fallback de emergencia
        df_sub = df.iloc[:, [0, 1, 2]].copy()
        df_sub.columns = ["Cantidad_Solicitada", "Item", "Presentacion"]
        df_sub["Costo"] = 0.0
        df_sub["Valor"] = 0.0
        df = df_sub
    else:
        df_sub = df.iloc[:, [idx_cant, idx_item, idx_pres]].copy()
        df_sub.columns = ["Cantidad_Solicitada", "Item", "Presentacion"]
        
        if idx_cost != -1 and idx_cost < len(df.columns):
            df_sub["Costo"] = df.iloc[:, idx_cost]
        else:
            df_sub["Costo"] = 0.0
            
        if idx_val != -1 and idx_val < len(df.columns):
            df_sub["Valor"] = df.iloc[:, idx_val]
        else:
            df_sub["Valor"] = 0.0
            
        df = df_sub
    
    # Limpieza:
    # 1. Eliminar filas que repiten la cabecera (ej. "Cant" o "Item")
    df = df[df["Item"] != "Item"]
    df = df[df["Cantidad_Solicitada"] != "Cant"]
    
    # 2. Eliminar filas donde Item esté vacío o nulo
    df = df[df["Item"].notna() & (df["Item"].str.strip() != "")]
    
    # 2.5. Limpieza extrema de Item (reemplazar \n y espacios múltiples)
    df["Item"] = df["Item"].astype(str).str.replace(r'\n+', ' ', regex=True).str.strip()
    df["Item"] = df["Item"].str.replace(r'\s+', ' ', regex=True)
    
    df["Cantidad_Solicitada"] = df["Cantidad_Solicitada"].apply(limpiar_cantidad)
    df["Costo"] = df["Costo"].apply(limpiar_cantidad)
    df["Valor"] = df["Valor"].apply(limpiar_cantidad)
    
    return df

def procesar_pdf(pdf_file, semana: str, tipo_requerimiento: str):
    """
    Procesa un archivo PDF (stream o ruta) y retorna un DataFrame listo para la BD.
    
    pdf_file: puede ser una ruta (str) o un objeto file-like (Streamlit uploader).
    """
    # Si es un objeto de Streamlit, pdfplumber puede leerlo directamente de la memoria?
    # extract_text y extract_table funcionan con pdfplumber.open(pdf_file)
    
    with pdfplumber.open(pdf_file) as pdf:
        # 1. Extraer Cabecera (de la primera página)
        primera_pagina = pdf.pages[0].extract_text() or ""
        id_orden, almacen_destino = extraer_cabecera(primera_pagina)
        
        if not id_orden:
            # Intento de respaldo o error
            # Podríamos intentar leer otras páginas si la cabecera se repite
            pass
            
        # 2. Extraer Tabla
        df_tabla = extraer_tabla(pdf)
        
        if df_tabla.empty:
            return pd.DataFrame(), f"No se encontraron tablas en el PDF."
            
        # 3. Enriquecimiento
        df_tabla["ID_Orden"] = id_orden
        df_tabla["Almacen_Destino"] = almacen_destino
        df_tabla["Semana"] = semana
        df_tabla["Tipo_Requerimiento"] = tipo_requerimiento
        
        # Validar que ID_Orden y Almacen_Destino no sean nulos
        if not id_orden or not almacen_destino:
            pass
            
        columnas_finales = [
            "ID_Orden", "Item", "Almacen_Destino", "Presentacion", 
            "Cantidad_Solicitada", "Semana", "Tipo_Requerimiento",
            "Costo", "Valor"
        ]
        df_final = df_tabla[columnas_finales]
        
        # 4. Consolidar cantidades (Agrupación)
        if not df_final.empty:
            # Crear índice secuencial para mantener orden original
            df_final = df_final.copy() # Evitar SettingWithCopy Warning
            df_final["Fila_Original"] = range(len(df_final))
            
            columnas_agrupamiento = [
                "ID_Orden", "Item", "Almacen_Destino", "Presentacion", "Semana", "Tipo_Requerimiento"
            ]
            
            df_final = df_final.groupby(columnas_agrupamiento, as_index=False, sort=False).agg({
                "Cantidad_Solicitada": "sum",
                "Costo": "mean",
                "Valor": "sum",
                "Fila_Original": "min" # Nos quedamos con la posición de la primera vez que apareció
            })
            
            # Reordenar columnas para mantener consistencia con database.py
            # NOTA: Costo y Valor se guardan ahora en despachos_reales, no en requerimientos_originales
            columnas_finales_db = [
                "ID_Orden", "Item", "Almacen_Destino", "Presentacion", 
                "Cantidad_Solicitada", "Semana", "Tipo_Requerimiento", "Fila_Original"
            ]
            # Solo incluir Costo/Valor en el df si las columnas existen
            df_final["Costo"] = 0.0
            df_final["Valor"] = 0.0
            df_final = df_final[columnas_finales_db + ["Costo", "Valor"]]
        
        return df_final, None

def extraer_cabecera_despacho(texto_pagina):
    """
    Extrae ID_Movimiento, ID_Orden_Ref y Fecha_Movimiento de despachos usando regex.
    """
    id_movimiento = None
    id_orden_ref = None
    fecha_movimiento = None
    
    # Movimiento entre almacenes #1180
    match_movimiento = re.search(r"Movimiento entre almacenes #(\d+)", texto_pagina)
    if match_movimiento:
        id_movimiento = int(match_movimiento.group(1))
        
    # Orden de movimiento: 1624
    match_orden = re.search(r"Orden de movimiento:\s*(\d+)", texto_pagina)
    if match_orden:
        id_orden_ref = int(match_orden.group(1))
        
    # Fecha del movimiento: 14/03/2026
    match_fecha = re.search(r"Fecha del movimiento:\s*(\d{2}/\d{2}/\d{4})", texto_pagina)
    if match_fecha:
        fecha_movimiento = match_fecha.group(1)
        
    return id_movimiento, id_orden_ref, fecha_movimiento

def extraer_tabla_despacho(pdf):
    """
    Extrae tablas de despachos, limpia texto de saltos de línea y filtra columnas.
    """
    all_rows = []
    
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_rows.extend(table)
                
    if not all_rows:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_rows)
    
    if df.empty:
        return df
        
    # [NUEVO] Detección Dinámica de Columnas en Despacho
    idx_cols = detectar_columnas(df)
    idx_cant = idx_cols["Cant"]
    idx_item = idx_cols["Item"]
    idx_cost = idx_cols.get("Costo", -1)
    idx_val  = idx_cols.get("Valor", -1)
    
    # Validar que no sean iguales o desbordados
    if idx_cant >= len(df.columns) or idx_item >= len(df.columns):
        # Fallback de emergencia
        df_sub = df.iloc[:, [0, 1]].copy()
        df_sub.columns = ["Cantidad_Entregada", "Item"]
        df_sub["Costo"] = 0.0
        df_sub["Valor"] = 0.0
        df = df_sub
    else:
        df_sub = df.iloc[:, [idx_cant, idx_item]].copy()
        df_sub.columns = ["Cantidad_Entregada", "Item"]
        
        if idx_cost != -1 and idx_cost < len(df.columns):
            df_sub["Costo"] = df.iloc[:, idx_cost]
        else:
            df_sub["Costo"] = 0.0
            
        if idx_val != -1 and idx_val < len(df.columns):
            df_sub["Valor"] = df.iloc[:, idx_val]
        else:
            df_sub["Valor"] = 0.0
            
        df = df_sub
    
    # Limpieza:
    df = df[df["Item"] != "Item"]
    df = df[df["Cantidad_Entregada"] != "Cant"]
    df = df[df["Item"].notna() & (df["Item"].str.strip() != "")]
    
    # Limpieza extrema de Item (reemplazar \n y espacios múltiples)
    df["Item"] = df["Item"].astype(str).str.replace(r'\n+', ' ', regex=True).str.strip()
    df["Item"] = df["Item"].str.replace(r'\s+', ' ', regex=True)
    
    df["Cantidad_Entregada"] = df["Cantidad_Entregada"].apply(limpiar_cantidad)
    df["Costo"] = df["Costo"].apply(limpiar_cantidad)
    df["Valor"] = df["Valor"].apply(limpiar_cantidad)
    
    return df

def procesar_pdf_despacho(pdf_file):
    """
    Procesa un archivo PDF de despacho y retorna un DataFrame listo para la BD.
    """
    with pdfplumber.open(pdf_file) as pdf:
        primera_pagina = pdf.pages[0].extract_text() or ""
        id_movimiento, id_orden_ref, fecha_movimiento = extraer_cabecera_despacho(primera_pagina)
        
        df_tabla = extraer_tabla_despacho(pdf)
        
        if df_tabla.empty:
            return pd.DataFrame(), f"No se encontraron tablas en el despacho."
            
        # Enriquecimiento
        df_tabla["ID_Movimiento"] = id_movimiento
        df_tabla["ID_Orden_Ref"] = id_orden_ref
        df_tabla["Fecha_Movimiento"] = fecha_movimiento
        
        # Consolidar cantidades por Item (sumar) en caso de repetirse
        if not df_tabla.empty:
            columnas_agrupamiento = ["ID_Movimiento", "ID_Orden_Ref", "Item", "Fecha_Movimiento"]
            df_tabla = df_tabla.groupby(columnas_agrupamiento, as_index=False, sort=False).agg({
                "Cantidad_Entregada": "sum",
                "Costo": "mean",
                "Valor": "sum"
            })
            
        columnas_finales = ["ID_Movimiento", "ID_Orden_Ref", "Item", "Cantidad_Entregada", "Fecha_Movimiento", "Costo", "Valor"]
        df_final = df_tabla[columnas_finales]
        
        return df_final, None

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        tipo_doc = sys.argv[1] # 'orden' o 'despacho'
        ruta_pdf = sys.argv[2]
        
        if os.path.exists(ruta_pdf):
            if tipo_doc == "orden":
                df, error = procesar_pdf(ruta_pdf, "Semana de Prueba", "Normal")
            elif tipo_doc == "despacho":
                df, error = procesar_pdf_despacho(ruta_pdf)
            else:
                print("Tipo de documento no soportado. Uso: python extractor.py <orden|despacho> <ruta_del_pdf>")
                sys.exit(1)
                
            if error:
                print(f"Error: {error}")
            else:
                print(df)
        else:
            print(f"Archivo no encontrado: {ruta_pdf}")
    else:
        print("Uso: python extractor.py <orden|despacho> <ruta_del_pdf>")
