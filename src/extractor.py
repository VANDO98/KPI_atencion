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
        almacen_destino = match_almacen.group(1).strip()
        
    return id_orden, almacen_destino

def extraer_tabla(pdf):
    """
    Extrae todas las tablas de todas las páginas y las concatena.
    """
    all_rows = []
    
    for page in pdf.pages:
        # extract_tables() retorna una lista de tablas listas
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_rows.extend(table)
            
    if not all_rows:
        return pd.DataFrame()
        
    # Convertir a DataFrame
    # Las cabeceras suelen estar en la primera fila, pero pueden repetirse.
    df = pd.DataFrame(all_rows)
    
    if df.empty:
        return df
        
    # Asignar nombres de columnas si coinciden con la cabecera
    # Cabeceras esperadas: ["Cant", "Item", "Presentacion", "Cant. a mover"]
    # Usamos las primeras filas para detectar
    
    # Renombrar columnas según posición (0, 1, 2)
    df = df.iloc[:, [0, 1, 2]] # Nos quedamos con Cant, Item, Presentacion
    df.columns = ["Cantidad_Solicitada", "Item", "Presentacion"]
    
    # Limpieza:
    # 1. Eliminar filas que repiten la cabecera (ej. "Cant" o "Item")
    df = df[df["Item"] != "Item"]
    df = df[df["Cantidad_Solicitada"] != "Cant"]
    
    # 2. Eliminar filas donde Item esté vacío o nulo
    df = df[df["Item"].notna() & (df["Item"].str.strip() != "")]
    
    # 3. Convertir Cantidad_Solicitada a float
    # Puede contener comas o puntos. Reemplazamos/limpiamos si es necesario.
    def convertir_cantidad(val):
        if pd.isna(val) or val == "":
            return 0.0
        try:
            # Eliminar espacios y convertir
            return float(str(val).strip())
        except ValueError:
            return 0.0
            
    df["Cantidad_Solicitada"] = df["Cantidad_Solicitada"].apply(convertir_cantidad)
    
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
            "Cantidad_Solicitada", "Semana", "Tipo_Requerimiento"
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
                "Fila_Original": "min" # Nos quedamos con la posición de la primera vez que apareció
            })
            
            # Reordenar columnas para mantener consistencia con database.py
            columnas_finales_db = [
                "ID_Orden", "Item", "Almacen_Destino", "Presentacion", 
                "Cantidad_Solicitada", "Semana", "Tipo_Requerimiento", "Fila_Original"
            ]
            df_final = df_final[columnas_finales_db]
        
        return df_final, None

if __name__ == "__main__":
    # Script de prueba (se requiere un PDF de prueba)
    import sys
    if len(sys.argv) > 1:
        ruta_pdf = sys.argv[1]
        if os.path.exists(ruta_pdf):
            df, error = procesar_pdf(ruta_pdf, "Semana de Prueba", "Normal")
            if error:
                print(f"Error: {error}")
            else:
                print(df)
        else:
            print(f"Archivo no encontrado: {ruta_pdf}")
    else:
        print("Uso: python extractor.py <ruta_del_pdf>")
