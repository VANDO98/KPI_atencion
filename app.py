import streamlit as st
import pandas as pd
import os
import src.database as db
import src.extractor as ext

# Configuración de la página
st.set_page_config(
    page_title="Extractor de Órdenes - Logística",
    page_icon="📋",
    layout="wide"
)

# Inicializar Base de Datos
if 'db_initialized' not in st.session_state:
    db.init_db()
    st.session_state.db_initialized = True

# Estado de la sesión para métricas
if 'ordenes_cargadas_sesion' not in st.session_state:
    st.session_state.ordenes_cargadas_sesion = 0

# --- PANEL LATERAL (Sidebar) ---
st.sidebar.title("📁 Cargar Requerimientos")

# 1. Carga de Archivos
archivos_pdf = st.sidebar.file_uploader(
    "Selecciona archivos PDF", 
    type="pdf", 
    accept_multiple_files=True,
    help="Arrastra o selecciona uno o varios archivos .pdf de Órdenes de Movimiento"
)

# 2. Selector de Semana
semanas = [f"Semana {i}" for i in range(1, 53)]
semana_seleccionada = st.sidebar.selectbox(
    "Selecciona la Semana",
    options=semanas,
    index=41 # Por defecto Semana 42 como en el ejemplo
)

# 3. Selector de Tipo
tipo_requerimiento = st.sidebar.radio(
    "Tipo de Requerimiento",
    options=["Normal", "Adicional"],
    horizontal=True
)

# 4. Botón de Acción
procesar_btn = st.sidebar.button("🚀 Procesar y Guardar", use_container_width=True)

# Lógica de Procesamiento
if procesar_btn:
    if not archivos_pdf:
        st.sidebar.warning("⚠️ Por favor, carga al menos un archivo PDF.")
    else:
        with st.spinner("Procesando documentos..."):
            total_items_insertados = 0
            ordenes_exitosas = 0
            errores = []
            
            for pdf_file in archivos_pdf:
                try:
                    # Procesar PDF
                    df_resultado, error = ext.procesar_pdf(
                        pdf_file, 
                        semana=semana_seleccionada, 
                        tipo_requerimiento=tipo_requerimiento
                    )
                    
                    if error:
                        errores.append(f"**{pdf_file.name}**: {error}")
                        continue
                        
                    if df_resultado.empty:
                        errores.append(f"**{pdf_file.name}**: No se extrajeron ítems.")
                        continue
                        
                    # Insertar en BD
                    filas_afectadas = db.insertar_requerimientos(df_resultado)
                    
                    if filas_afectadas > 0:
                        total_items_insertados += filas_afectadas
                        ordenes_exitosas += 1
                    else:
                        errores.append(f"**{pdf_file.name}**: No se insertaron filas (posiblemente vacías o duplicadas).")
                        
                except Exception as e:
                    errores.append(f"**{pdf_file.name}**: Error inesperado ({str(e)})")
                    
            # Mostrar Resultados
            if ordenes_exitosas > 0:
                st.sidebar.success(f"✅ ¡Éxito! Se procesaron {ordenes_exitosas} órdenes correctamente.")
                st.session_state.ordenes_cargadas_sesion += ordenes_exitosas
                
            if errores:
                with st.sidebar.expander("⚠️ Ver avisos/errores"):
                    for err in errores:
                        st.write(err)

# --- PANEL CENTRAL (Main View) ---
st.title("📋 Historial de Órdenes Procesadas")

# Métricas
metricas = db.obtener_metricas()
col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="Total de Órdenes Históricas", 
        value=metricas["total_ordenes"]
    )

with col2:
    st.metric(
        label="Órdenes Cargadas en la sesión actual", 
        value=st.session_state.ordenes_cargadas_sesion
    )

st.divider()

# Tabla de Historial
st.subheader("Órdenes Registradas")

historial_df = db.obtener_historial()

if not historial_df.empty:
    # Renombrar columnas para la vista
    vista_df = historial_df.rename(columns={
        "ID_Orden": "ID Orden",
        "Almacen_Destino": "Almacén Destino",
        "Semana": "Semana",
        "Tipo_Requerimiento": "Tipo"
    })
    
    # Mostrar DataFrame
    st.dataframe(
        vista_df, 
        use_container_width=True,
        hide_index=True
    )
    
    # --- NUEVO: Visor de Detalles ---
    st.divider()
    st.subheader("🔍 Ver Detalles de una Orden")
    
    # Selector de Orden
    ordenes_disponibles = historial_df["ID_Orden"].tolist()
    
    col_sel, _ = st.columns([1, 2])
    with col_sel:
        orden_seleccionada = st.selectbox(
            "Selecciona una Orden para ver sus ítems:",
            options=ordenes_disponibles,
            format_func=lambda x: f"Orden #{x}"
        )
        
    if orden_seleccionada:
        items_df = db.obtener_items_por_orden(orden_seleccionada)
        if not items_df.empty:
            # Renombrar columnas para la vista
            items_vista = items_df.rename(columns={
                "Cantidad_Solicitada": "Cantidad",
                "Presentacion": "Presentación"
            })
            
            st.dataframe(
                items_vista,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("No se encontraron ítems para esta orden.")
            
else:
    st.info("ℹ️ No hay órdenes procesadas en la base de datos. Utiliza el panel lateral para cargar archivos.")

# Pie de página o información adicional
st.sidebar.divider()
st.sidebar.caption("Desarrollado para Área de Logística HORECA")
