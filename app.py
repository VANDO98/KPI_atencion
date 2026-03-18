import streamlit as st
import pandas as pd
import os
import src.database as db
import src.extractor as ext

# Configuración de la página
st.set_page_config(
    page_title="KPI Logística - Fill Rate",
    page_icon="📊",
    layout="wide"
)

# Inicializar Base de Datos
if 'db_initialized' not in st.session_state:
    db.init_db()
    st.session_state.db_initialized = True

# Estado de la sesión para métricas
if 'ordenes_cargadas_sesion' not in st.session_state:
    st.session_state.ordenes_cargadas_sesion = 0
if 'despachos_cargados_sesion' not in st.session_state:
    st.session_state.despachos_cargados_sesion = 0

st.title("📋 Extractor de Órdenes y Control de KPI")

# Crear Pestañas
tab_requerimientos, tab_despachos, tab_kpi = st.tabs([
    "📋 1. Requerimientos Originales", 
    "🚚 2. Despachos Reales", 
    "📊 3. Panel de Reportes KPI"
])

# --- PESTAÑA 1: REQUERIMIENTOS ORIGINALES ---
with tab_requerimientos:
    st.header("Cargar Órdenes de Movimiento")
    
    col_izq, col_der = st.columns([1, 2])
    
    with col_izq:
        st.subheader("📁 Cargar PDFs")
        archivos_pdf = st.file_uploader(
            "Selecciona archivos PDF de Órdenes", 
            type="pdf", 
            accept_multiple_files=True,
            key="pdf_ordenes",
            help="Arrastra o selecciona uno o varios archivos de Órdenes de Movimiento"
        )
        
        semanas = [f"Semana {i}" for i in range(1, 53)]
        semana_seleccionada = st.selectbox(
            "Selecciona la Semana", 
            options=semanas, 
            index=41, 
            key="sem_ordenes"
        )
        
        tipo_requerimiento = st.radio(
            "Tipo de Requerimiento", 
            options=["Normal", "Adicional"], 
            horizontal=True, 
            key="tipo_ordenes"
        )
        
        procesar_btn = st.button("🚀 Procesar y Guardar Órdenes", use_container_width=True, key="btn_ordenes")
        
        if procesar_btn:
            if not archivos_pdf:
                st.warning("⚠️ Por favor, carga al menos un archivo PDF.")
            else:
                with st.spinner("Procesando documentos..."):
                    ordenes_exitosas = 0
                    errores = []
                    
                    for pdf_file in archivos_pdf:
                        try:
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
                                
                            filas_afectadas = db.insertar_requerimientos(df_resultado)
                            if filas_afectadas > 0:
                                ordenes_exitosas += 1
                            else:
                                errores.append(f"**{pdf_file.name}**: No se insertaron filas.")
                        except Exception as e:
                            errores.append(f"**{pdf_file.name}**: Error inesperado ({str(e)})")
                            
                    if ordenes_exitosas > 0:
                        st.success(f"✅ Se procesaron {ordenes_exitosas} órdenes correctamente.")
                        st.session_state.ordenes_cargadas_sesion += ordenes_exitosas
                    if errores:
                        with st.expander("⚠️ Ver avisos/errores"):
                            for err in errores: st.write(err)

    with col_der:
        st.subheader("📋 Historial de Órdenes")
        historial_df = db.obtener_historial()
        
        if not historial_df.empty:
            vista_df = historial_df.rename(columns={
                "ID_Orden": "ID Orden",
                "Almacen_Destino": "Almacén",
                "Tipo_Requerimiento": "Tipo"
            })
            st.dataframe(vista_df, use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("🔍 Ver Detalles de una Orden")
            ordenes_disponibles = historial_df["ID_Orden"].tolist()
            orden_seleccionada = st.selectbox(
                "Selecciona una Orden:", 
                options=ordenes_disponibles, 
                format_func=lambda x: f"Orden #{x}",
                key="sel_orden"
            )
            
            if orden_seleccionada:
                items_df = db.obtener_items_por_orden(orden_seleccionada)
                if not items_df.empty:
                    items_vista = items_df.rename(columns={
                        "Cantidad_Solicitada": "Cant. Solicitada",
                        "Presentacion": "Presentación"
                    })
                    st.dataframe(items_vista, use_container_width=True, hide_index=True)
        else:
            st.info("ℹ️ No hay órdenes procesadas en la base de datos.")

# --- PESTAÑA 2: DESPACHOS REALES [NUEVO] ---
with tab_despachos:
    st.header("Cargar Movimientos entre Almacenes")
    
    col_izq_d, col_der_d = st.columns([1, 2])
    
    with col_izq_d:
        st.subheader("📁 Cargar PDFs de Despacho")
        archivos_despacho = st.file_uploader(
            "Selecciona archivos PDF de Despacho", 
            type="pdf", 
            accept_multiple_files=True,
            key="pdf_despachos",
            help="Carga los PDFs de Movimiento entre almacenes"
        )
        
        procesar_despacho_btn = st.button("🚀 Procesar y Guardar Despachos", use_container_width=True, key="btn_despachos")
        
        if procesar_despacho_btn:
            if not archivos_despacho:
                st.warning("⚠️ Por favor, carga al menos un archivo PDF de despacho.")
            else:
                with st.spinner("Procesando despachos..."):
                    despachos_exitosos = 0
                    errores_d = []
                    
                    for pdf_file in archivos_despacho:
                        try:
                            df_res, err = ext.procesar_pdf_despacho(pdf_file)
                            if err:
                                errores_d.append(f"**{pdf_file.name}**: {err}")
                                continue
                            
                            filas_d = db.insertar_despachos(df_res)
                            if filas_d > 0:
                                despachos_exitosos += 1
                            else:
                                errores_d.append(f"**{pdf_file.name}**: No se insertaron registros.")
                        except Exception as e:
                            errores_d.append(f"**{pdf_file.name}**: Error inesperado ({str(e)})")
                            
                    if despachos_exitosos > 0:
                        st.success(f"✅ Se procesaron {despachos_exitosos} despachos correctamente.")
                        st.session_state.despachos_cargados_sesion += despachos_exitosos
                    if errores_d:
                        with st.expander("⚠️ Ver errores"):
                            for err in errores_d: st.write(err)

    with col_der_d:
        st.subheader("📋 Historial de Despachos")
        historial_d_df = db.obtener_historial_despachos()
        if not historial_d_df.empty:
            st.dataframe(historial_d_df, use_container_width=True, hide_index=True)
        else:
            st.info("ℹ️ No hay despachos procesados en la base de datos.")

# --- PESTAÑA 3: PANEL DE REPORTES KPI [NUEVO] ---
with tab_kpi:
    st.header("Reporte de KPIs y Backorders")
    
    # 1. Filtros
    col_f1, col_f2, col_f3 = st.columns(3)
    
    # Traer todos los datos para extraer los filtros dinámicos
    df_all_kpi = db.obtener_reporte_kpi()
    
    with col_f1:
        semanas_filtro = ["Todas"] + [f"Semana {i}" for i in range(1, 53)]
        sem_fil = st.selectbox("Filtrar por Semana", options=semanas_filtro, index=0, key="fil_sem")
    
    with col_f2:
        almacenes = ["Todos"] + df_all_kpi["Almacen_Destino"].unique().tolist() if not df_all_kpi.empty else ["Todos"]
        alm_fil = st.selectbox("Filtrar por Almacén", options=almacenes, index=0, key="fil_alm")
        
    with col_f3:
        tipo_fil = st.selectbox("Filtrar por Tipo", options=["Todos", "Normal", "Adicional"], index=0, key="fil_tipo")
        
    st.divider()
    
    # 2. Aplicar Filtros
    df_kpi = db.obtener_reporte_kpi(
        semana=None if sem_fil == "Todas" else sem_fil,
        almacen=None if alm_fil == "Todos" else alm_fil,
        tipo=None if tipo_fil == "Todos" else tipo_fil
    )
    
    if not df_kpi.empty:
        # Métricas Globales
        suma_solicitada = df_kpi["Cantidad_Solicitada"].sum()
        suma_entregada = df_kpi["Cantidad_Entregada"].sum()
        fill_rate_global = (suma_entregada / suma_solicitada) * 100 if suma_solicitada > 0 else 0
        
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.metric(label="Fill Rate Global", value=f"{fill_rate_global:.2f}%")
        with m_col2:
            st.metric(label="Total Items Analizados", value=len(df_kpi))
            
        st.divider()
        
        # 3. Tabla Backorders
        st.subheader("📋 Backorders (Saldos Pendientes)")
        df_backorders = df_kpi[df_kpi["Cantidad_Pendiente"] > 0]
        
        if not df_backorders.empty:
            df_backorders = df_backorders.sort_values(by="Cantidad_Pendiente", ascending=False)
            
            # Renombrar para vista
            back_vista = df_backorders[[
                "ID_Orden", "Item", "Almacen_Destino", "Cantidad_Solicitada", 
                "Cantidad_Entregada", "Cantidad_Pendiente"
            ]].rename(columns={
                "Cantidad_Solicitada": "Req. Original",
                "Cantidad_Entregada": "Entregado",
                "Cantidad_Pendiente": "Pendiente"
            })
            
            st.dataframe(back_vista, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 ¡No hay Backorders! Todo lo solicitado fue entregado para estos filtros.")
    else:
        st.info("ℹ️ No hay datos que coincidan con los filtros seleccionados.")

st.sidebar.divider()
st.sidebar.caption("Fase 2 - Gestión de KPIs y Despachos")
