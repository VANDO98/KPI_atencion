from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import pandas as pd
import os
import io
import re

import src.database as db
import src.extractor as ext
from urllib.parse import quote

app = FastAPI(title="KPI Logística API")

# Inicializar DB (y recrear vista KPI) al arrancar
db.init_db()

# Asegurar que existen carpetas
if not os.path.exists("static"):
    os.makedirs("static")
if not os.path.exists("data/diagnostic_uploads"):
    os.makedirs("data/diagnostic_uploads")

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join("static", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse(content="<h1>Frontend no encontrado</h1><p>Cargando archivos...", status_code=200)
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

from typing import List

@app.post("/api/upload/orden")
async def upload_orden(
    files: List[UploadFile] = File(...), 
    semana: str = Query(...), 
    tipo_requerimiento: str = Query(...)
):
    try:
        total_items = 0
        errores = []
        
        for file in files:
            try:
                content = await file.read()
                
                pdf_file = io.BytesIO(content)
                df_resultado, error = ext.procesar_pdf(pdf_file, semana=semana, tipo_requerimiento=tipo_requerimiento)
                
                if error:
                    errores.append(f"{file.filename}: {error}")
                    continue
                if df_resultado.empty:
                    errores.append(f"{file.filename}: No se extrajeron ítems.")
                    continue
                    
                filas = db.insertar_requerimientos(df_resultado)
                total_items += filas
            except Exception as e:
                errores.append(f"{file.filename}: Error {str(e)}")
                
        if errores:
            return {
                "success": total_items > 0, 
                "message": f"Se procesaron {total_items} registros.",
                "errores": errores
            }
        return {"success": True, "message": f"Órdenes procesadas. {total_items} registros guardados."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload/despacho")
async def upload_despacho(files: List[UploadFile] = File(...)):
    try:
        total_items = 0
        errores = []
        
        for file in files:
            try:
                content = await file.read()
                
                pdf_file = io.BytesIO(content)
                df_resultado, error = ext.procesar_pdf_despacho(pdf_file)
                if error:
                    errores.append(f"{file.filename}: {error}")
                    continue
                if df_resultado.empty:
                    errores.append(f"{file.filename}: No se encontraron tablas.")
                    continue
                    
                filas = db.insertar_despachos(df_resultado)
                total_items += filas
            except Exception as e:
                errores.append(f"{file.filename}: Error {str(e)}")
                
        if errores:
            return {
                "success": total_items > 0, 
                "message": f"Se procesaron {total_items} registros.",
                "errores": errores
            }
        return {"success": True, "message": f"Despachos procesados. {total_items} registros guardados."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/kpi")
async def get_kpi(
    semana: str = None, 
    almacen: str = None, 
    tipo: str = None
):
    df_kpi = db.obtener_reporte_kpi(
        semana=semana if semana and semana != "Todas" else None,
        almacen=almacen if almacen and almacen != "Todos" else None,
        tipo=tipo if tipo and tipo != "Todos" else None
    )
    
    df_maestro = db.obtener_maestro_insumos()
    if not df_maestro.empty:
        df_kpi["Item_Limpio"] = df_kpi["Item"].apply(db.limpiar_texto)
        df_kpi = df_kpi.merge(df_maestro[["Item_Limpio", "Categoria"]], on="Item_Limpio", how="left")
        df_kpi["Categoria"] = df_kpi["Categoria"].fillna("Sin Categoría")
    else:
        df_kpi["Categoria"] = "Sin Categoría"
        
    # --- [NUEVO] Calcular % Peso de Regularizaciones (Ponderado) ---
    df_reg = df_kpi[df_kpi["Tipo_Requerimiento"].isin(["Regularización", "Regularizacion"])]
    volumen_reg = df_reg["Cantidad_Entregada"].sum() if not df_reg.empty else 0
    volumen_total_general = df_kpi["Cantidad_Entregada"].sum()
    porcentaje_regularizacion = (volumen_reg / volumen_total_general) * 100 if volumen_total_general > 0 else 0
    # -------------------------------------------------------------
        
    # Excluir Regularizaciones del cálculo de Fill Rate y KPIs
    df_kpi = df_kpi[~df_kpi["Tipo_Requerimiento"].isin(["Regularización", "Regularizacion"])]
        
    # 1. Fill Rate Global por Volumen
    suma_solicitada = df_kpi["Cantidad_Solicitada"].sum()
    suma_entregada = df_kpi["Cantidad_Entregada"].sum()
    fill_rate_volumen = (suma_entregada / suma_solicitada) * 100 if suma_solicitada > 0 else 0
    
    # 2. Fill Rate Global por Ítem (Promedio Simple)
    fill_rate_item = df_kpi["Fill_Rate_Porcentaje"].mean()
    
    # [NUEVO] 2.5. Fill Rate Financiero
    df_fin = df_kpi[df_kpi["Costo"] > 0]
    monto_solicitado = 0.0
    monto_entregado = 0.0
    if df_fin.empty:
        fill_rate_financiero = 0.0
    else:
        monto_solicitado = (df_fin["Cantidad_Solicitada"] * df_fin["Costo"]).sum()
        monto_entregado = (df_fin["Cantidad_Entregada"] * df_fin["Costo"]).sum()
        fill_rate_financiero = (monto_entregado / monto_solicitado) * 100 if monto_solicitado > 0 else 0.0
        
    # 3. Datos de Adicionales vs Normales (Ponderado por Conteo de Ítems/Lineas)
    df_normales = df_kpi[df_kpi["Tipo_Requerimiento"] == "Normal"]
    df_adicionales = df_kpi[df_kpi["Tipo_Requerimiento"] == "Adicional"]
    items_normales_count = len(df_normales)
    items_adicionales_count = len(df_adicionales)
    porcentaje_adicionales = (items_adicionales_count / items_normales_count) * 100 if items_normales_count > 0 else 0
    fill_rate_adicional = df_adicionales["Fill_Rate_Porcentaje"].mean() if not df_adicionales.empty else 0
    
    # 4. Porcentaje de Órdenes Perfectas (POP)
    df_ordenes_pop = df_kpi.groupby("ID_Orden")["Cantidad_Pendiente"].sum().reset_index()
    total_ordenes = len(df_ordenes_pop)
    ordenes_perfectas = len(df_ordenes_pop[df_ordenes_pop["Cantidad_Pendiente"] <= 0])
    pop = (ordenes_perfectas / total_ordenes) * 100 if total_ordenes > 0 else 0

    # 5. Items Críticos (Deuda) - Actual vs Anterior
    df_deuda = df_kpi.groupby("Item")["Cantidad_Pendiente"].sum().reset_index()
    df_deuda = df_deuda[df_deuda["Cantidad_Pendiente"] > 0].sort_values(by="Cantidad_Pendiente", ascending=False)
    items_criticos_actual = df_deuda.head(5).to_dict(orient="records")
    
    items_criticos_anterior = []
    if semana and "Semana" in semana:
        try:
            num = int(semana.split()[1])
            if num > 1:
                semana_ant = f"Semana {num - 1}"
                df_ant = db.obtener_reporte_kpi(
                    semana=semana_ant,
                    almacen=almacen if almacen and almacen != "Todos" else None,
                    tipo=tipo if tipo and tipo != "Todos" else None
                )
                if not df_ant.empty:
                    df_deuda_ant = df_ant.groupby("Item")["Cantidad_Pendiente"].sum().reset_index()
                    df_deuda_ant = df_deuda_ant[df_deuda_ant["Cantidad_Pendiente"] > 0].sort_values(by="Cantidad_Pendiente", ascending=False)
                    items_criticos_anterior = df_deuda_ant.head(5).to_dict(orient="records")
        except Exception:
            pass

    # 6. Backorders
    df_backorders = df_kpi[df_kpi["Cantidad_Pendiente"] > 0].sort_values(by="Cantidad_Pendiente", ascending=False)
    backorders_json = df_backorders.to_dict(orient="records")
    
    return {
        "fill_rate_volumen": round(fill_rate_volumen, 2),
        "fill_rate_item": round(fill_rate_item, 2),
        "fill_rate_financiero": round(fill_rate_financiero, 2),
        "monto_solicitado": round(float(monto_solicitado), 2),
        "monto_entregado": round(float(monto_entregado), 2),
        "total_items": len(df_kpi),
        "items_adicionales": items_adicionales_count,
        "porcentaje_adicionales": round(porcentaje_adicionales, 2),
        "fill_rate_adicional": round(fill_rate_adicional, 2),
        "pop": round(pop, 2),
        "items_criticos_actual": items_criticos_actual,
        "items_criticos_anterior": items_criticos_anterior,
        "backorders": backorders_json,
        "porcentaje_regularizacion": round(porcentaje_regularizacion, 2),
        "data_completa": df_kpi.to_dict(orient="records")
    }

@app.get("/api/orden/{id_orden}/items")
async def get_orden_items(id_orden: int):
    """
    Devuelve los ítems detallados de una orden específica con sus costos y estado (para el Modal).
    """
    df_kpi = db.obtener_reporte_kpi(semana=None)
    df_orden = df_kpi[df_kpi["ID_Orden"] == id_orden].copy()
    
    if df_orden.empty:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
        
    df_orden["Valor_Unitario"] = df_orden["Costo"].round(2)
    df_orden["Soli"] = df_orden["Cantidad_Solicitada"]
    df_orden["Entr"] = df_orden["Cantidad_Entregada"]
    df_orden["Pend"] = df_orden["Cantidad_Pendiente"]
    df_orden["Almacen"] = df_orden["Almacen_Destino"]
    
    # Solo devolver las columnas necesarias
    res = df_orden[["Item", "Almacen", "Valor_Unitario", "Soli", "Entr", "Pend"]].to_dict(orient="records")
    return {"success": True, "items": res}

@app.get("/api/report/excel")
async def get_excel_report(semana: str = "Todas"):
    df_kpi = db.obtener_reporte_kpi(semana=semana if semana != "Todas" else None)
    
    # Excluir Regularizaciones
    if not df_kpi.empty:
        df_kpi = df_kpi[~df_kpi["Tipo_Requerimiento"].isin(["Regularización", "Regularizacion"])]
    
    if df_kpi.empty:
        raise HTTPException(status_code=400, detail="No hay datos para esta semana.")
        
    df_no_atendidos = df_kpi[df_kpi["Cantidad_Pendiente"] > 0]
    if df_no_atendidos.empty:
        raise HTTPException(status_code=400, detail="🎉 No hay backorders (no atendidos) para esta semana.")

    reporte = []
    # Agrupamos por Almacén de Destino (Área)
    for area, group in df_no_atendidos.groupby("Almacen_Destino"):
        # Calcular el Fill Rate porcentual GLOBAL de dicha área (usando todo df_kpi de esa area)
        df_area_total = df_kpi[df_kpi["Almacen_Destino"] == area]
        suma_sol = df_area_total["Cantidad_Solicitada"].sum()
        suma_ent = df_area_total["Cantidad_Entregada"].sum()
        fill_rate_area = (suma_ent / suma_sol) * 100 if suma_sol > 0 else 0
        
        for _, row in group.iterrows():
            item_nombre = row["Item"]
            unidad = row.get("Unidad")
            if pd.notna(unidad) and unidad:
                item_nombre = f'{item_nombre} ({unidad})'
                
            reporte.append({
                "Área": area,
                "Fill Rate Global Área": f"{fill_rate_area:.2f}%",
                "Orden": row["ID_Orden"],
                "Tipo": row["Tipo_Requerimiento"],
                "Item": item_nombre,
                "Solicitado": row["Cantidad_Solicitada"],
                "Entregado": row["Cantidad_Entregada"],
                "Pendiente (Deuda)": row["Cantidad_Pendiente"],
                "Costo Unit.": row["Costo"],
                "Valor Solicitado": row["Valor"]
            })

    df_export = pd.DataFrame(reporte)
    
    # Buffer en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name="No Atendidos")
    output.seek(0)
    
    filename = f"Reporte_NoAtendidos_{semana.replace(' ', '_')}.xlsx"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    )

@app.get("/api/report/adicionales/excel")
async def get_excel_adicionales(semana: str = "Todas"):
    df_kpi = db.obtener_reporte_kpi(semana=semana if semana != "Todas" else None)
    
    if not df_kpi.empty:
        df_adicionales = df_kpi[df_kpi["Tipo_Requerimiento"].isin(["Adicional"])]
    else:
        df_adicionales = pd.DataFrame()
        
    if df_adicionales.empty:
        raise HTTPException(status_code=400, detail="🎉 No hay pedidos adicionales para esta semana.")

    reporte = []
    # Agrupamos por Almacén de Destino (Área)
    for area, group in df_adicionales.groupby("Almacen_Destino"):
        for _, row in group.iterrows():
            item_nombre = row["Item"]
            unidad = row.get("Unidad")
            if pd.notna(unidad) and unidad:
                item_nombre = f'{item_nombre} ({unidad})'
                
            reporte.append({
                "Área": area,
                "Orden": row["ID_Orden"],
                "Semana": row["Semana"],
                "Item": item_nombre,
                "Solicitado": row["Cantidad_Solicitada"],
                "Entregado": row["Cantidad_Entregada"],
                "Pendiente (Deuda)": row["Cantidad_Pendiente"],
                "Costo Unit.": row["Costo"],
                "Valor Solicitado": row["Valor"]
            })

    df_export = pd.DataFrame(reporte)
    
    # Buffer en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name="Adicionales")
    output.seek(0)
    
    filename = f"Reporte_Adicionales_{semana.replace(' ', '_')}.xlsx"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    )

@app.get("/api/history")
async def get_history():
    historial_o = db.obtener_historial().to_dict(orient="records")
    historial_d = db.obtener_historial_despachos().to_dict(orient="records")
    
    # [NUEVO] Determinar la última semana subida
    # Como historial_o está ordenado por ID_Orden DESC, el primero es el más nuevo.
    last_semana = "Semana 1" # Valor por defecto
    if historial_o:
        last_semana = historial_o[0]["Semana"]
    elif historial_d:
        # Si no hay órdenes pero hay despachos, buscar en reporte_kpi para esa orden?
        pass
        
    # Obtener listas únicas para filtros de UI
    df_all = db.obtener_reporte_kpi()
    almacenes = df_all["Almacen_Destino"].unique().tolist() if not df_all.empty else []
    
    return {
        "ordenes": historial_o,
        "despachos": historial_d,
        "almacenes": almacenes,
        "last_semana": last_semana
    }

from pydantic import BaseModel

class UpdateTipoRequest(BaseModel):
    id_orden: int
    nuevo_tipo: str

@app.post("/api/orden/update_tipo")
async def update_tipo_orden(req: UpdateTipoRequest):
    try:
        filas = db.actualizar_tipo_orden(req.id_orden, req.nuevo_tipo)
        if filas == 0:
            return {"success": False, "message": "No se encontró la orden o no hubo cambios."}
        return {"success": True, "message": f"Orden {req.id_orden} actualizada a {req.nuevo_tipo}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UpdateOrdenRequest(BaseModel):
    id_orden: int
    semana: str
    tipo: str

@app.get("/api/ordenes")
async def listar_ordenes():
    try:
        df = db.obtener_lista_ordenes()
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/orden/update")
async def update_orden(req: UpdateOrdenRequest):
    try:
        filas = db.actualizar_orden(req.id_orden, req.semana, req.tipo)
        if filas == 0:
            return {"success": False, "message": "No se encontró la orden o no hubo cambios."}
        return {"success": True, "message": f"Orden {req.id_orden} actualizada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/ordenes/{id_orden}")
async def delete_orden(id_orden: int):
    try:
        filas = db.eliminar_orden(id_orden)
        if filas == 0:
            return {"success": False, "message": "No se encontró la orden."}
        return {"success": True, "message": f"Orden {id_orden} eliminada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/despachos/huerfanos")
async def listar_despachos_huerfanos(semana: str = "Todas", almacen: str = "Todos"):
    try:
        import pandas as pd
        with db.get_connection() as conn:
            # Traemos todo, necesitamos Semana y Almacen para aplicar el filtro
            df_req = pd.read_sql("SELECT ID_Orden, Item, Semana, Almacen_Destino FROM requerimientos_originales", conn)
            df_desp = pd.read_sql("SELECT ID_Movimiento, ID_Orden_Ref, Item, Cantidad_Entregada, Fecha_Registro FROM despachos_reales", conn)

        if df_desp.empty:
            return {"fantasmas": [], "desajustes_nombre": []}

        # Aplicar limpieza de texto
        df_req["Item_Limpio"] = df_req["Item"].apply(db.limpiar_texto)
        df_desp["Item_Limpio"] = df_desp["Item"].apply(db.limpiar_texto)

        # 1. Buscar Huérfanos Totales (Fuzzy Match)
        df_merged_fuzzy = df_desp.merge(df_req, left_on=["ID_Orden_Ref", "Item_Limpio"], right_on=["ID_Orden", "Item_Limpio"], how="left")
        df_huerfanos = df_merged_fuzzy[df_merged_fuzzy["ID_Orden"].isna()].copy()

        if df_huerfanos.empty:
            return {"fantasmas": [], "desajustes_nombre": []}

        # 2. Separar listas
        ordenes_existentes = df_req["ID_Orden"].astype(str).unique()

        # Fantasmas: ID_Orden_Ref no existe en requerimientos
        df_fantasmas = df_huerfanos[~df_huerfanos["ID_Orden_Ref"].astype(str).isin(ordenes_existentes)]
        
        # Desajustes: ID_Orden_Ref SÍ existe, pero el Item no cruzó (Fuzzy Fail)
        df_desajustes = df_huerfanos[df_huerfanos["ID_Orden_Ref"].astype(str).isin(ordenes_existentes)].copy()

        # Agregamos metadata (Semana, Almacén) a los desajustes cruzando de nuevo con la tabla master de ordenes
        # para saber a qué semana/almacén pertenecen. Solo con ID_Orden group_by para que no se dupliquen.
        with db.get_connection() as conn:
            df_req_meta = pd.read_sql("SELECT ID_Orden, Semana, Almacen_Destino FROM requerimientos_originales GROUP BY ID_Orden", conn)
            
        # [FIX] Eliminar columnas previas para evitar Semana_x, Semana_y tras el merge
        df_desajustes = df_desajustes.drop(columns=["Semana", "Almacen_Destino"], errors="ignore")
        df_desajustes = df_desajustes.merge(df_req_meta, left_on="ID_Orden_Ref", right_on="ID_Orden", how="left")

        # Aplicar Filtros solicitados
        if semana and semana != "Todas":
            df_desajustes = df_desajustes[df_desajustes["Semana"] == semana]
        if almacen and almacen != "Todos":
            df_desajustes = df_desajustes[df_desajustes["Almacen_Destino"] == almacen]

        # Renombrar columnas para el JSON
        # Item_x viene de df_desp (el nombre real escrito en el despacho)
        df_fantasmas = df_fantasmas[["ID_Movimiento", "ID_Orden_Ref", "Item_x", "Cantidad_Entregada", "Fecha_Registro"]].rename(columns={"Item_x": "Item"})
        df_desajustes = df_desajustes[["ID_Movimiento", "ID_Orden_Ref", "Item_x", "Cantidad_Entregada", "Fecha_Registro"]].rename(columns={"Item_x": "Item"})

        dict_items_req = df_req.groupby("ID_Orden")["Item"].apply(list).to_dict()
        desajustes_json = df_desajustes.to_dict(orient="records")
        for row in desajustes_json:
            # [FIX] Conversión segura para evitar errores con NaNs
            try:
                id_ref = int(row["ID_Orden_Ref"])
                row["Opciones_Items"] = dict_items_req.get(id_ref, [])
            except (ValueError, TypeError):
                row["Opciones_Items"] = []

        return {
            "fantasmas": df_fantasmas.to_dict(orient="records"),
            "desajustes_nombre": desajustes_json
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CorregirDespachoRequest(BaseModel):
    id_movimiento: int
    item_original: str
    item_nuevo: str

@app.post("/api/despacho/corregir_item")
async def corregir_item(req: CorregirDespachoRequest):
    try:
        filas = db.corregir_item_despacho(req.id_movimiento, req.item_original, req.item_nuevo)
        if filas == 0:
            return {"success": False, "message": "No se encontró el ítem original o el movimiento."}
        return {"success": True, "message": f"Ítem corregido exitosamente a {req.item_nuevo}."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ForzarCumplimientoRequest(BaseModel):
    id_orden: int
    item: str

@app.post("/api/orden/forzar_cumplimiento")
async def api_forzar_cumplimiento(req: ForzarCumplimientoRequest):
    try:
        filas = db.forzar_cumplimiento(req.id_orden, req.item)
        if filas == 0:
            return {"success": False, "message": "No se encontró el ítem en la orden original."}
        # Invocamos también que se recalcule si es necesario, pero las Views lo hacen On-the-fly
        return {"success": True, "message": "Ítem marcado como cumplido al 100%."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reports/summary")
async def get_reports_summary():
    try:
        df = db.obtener_reporte_kpi()
        if df.empty:
            return {"semanas": [], "almacenes": [], "distribucion_tipo": {}}

        # 1. Resumen por SEMANA
        # Intenta extraer el número de la semana de forma más robusta
        def extract_week_num(s):
            if not s: return 0
            nums = re.findall(r'\d+', str(s))
            return int(nums[0]) if nums else 0
            
        df['Semana_Num'] = df['Semana'].apply(extract_week_num)
        
        # Agrupar asegurando que no perdamos datos si Semana_Num falla
        resumen_semanal = df.groupby(['Semana', 'Semana_Num']).agg({
            'ID_Orden': 'nunique',
            'Item': 'count',
            'Cantidad_Solicitada': 'sum',
            'Cantidad_Entregada': 'sum',
            'Fill_Rate_Porcentaje': 'mean'
        }).reset_index()
        
        resumen_semanal = resumen_semanal.sort_values('Semana_Num', ascending=True).to_dict(orient="records")

        # 2. Resumen por TIPO
        dist_tipo = df.groupby('Tipo_Requerimiento').agg({
            'ID_Orden': 'nunique',
            'Item': 'count'
        }).to_dict(orient="index")

        # 3. Resumen por ALMACÉN
        resumen_almacen = df.groupby('Almacen_Destino').agg({
            'ID_Orden': 'nunique',
            'Fill_Rate_Porcentaje': 'mean'
        }).sort_values('Fill_Rate_Porcentaje', ascending=False).reset_index().to_dict(orient="records")

        return {
            "semanas": resumen_semanal,
            "distribucion_tipo": dist_tipo,
            "almacenes": resumen_almacen
        }
    except Exception as e:
        print(f"Error en reports summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/report/raw/excel")
async def get_raw_excel_report(semana: str = Query(...)):
    """
    Genera un reporte Excel con toda la data en bruto de una semana específica.
    """
    try:
        df = db.obtener_reporte_kpi(semana=semana)
        if df.empty:
            raise HTTPException(status_code=404, detail="No hay datos para la semana seleccionada.")
            
        # Seleccionar y renombrar columnas solicitadas por el usuario
        # Semana/Orden/Item/cantidad_solicitada/Atendida/tipo
        report_df = df[[
            "Semana", "ID_Orden", "Item", "Cantidad_Solicitada", 
            "Cantidad_Entregada", "Costo", "Valor", "Tipo_Requerimiento", "Almacen_Destino"
        ]].copy()
        
        report_df.columns = [
            "Semana", "Orden", "Ítem", "Cantidad Solicitada", 
            "Atendida", "Costo Unitario", "Valor Total", "Tipo Requerimiento", "Almacén"
        ]
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            report_df.to_excel(writer, index=False, sheet_name='Data_Bruta')
            
            # Formato estético básico
            workbook = writer.book
            worksheet = writer.sheets['Data_Bruta']
            header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
            for col_num, value in enumerate(report_df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 15)

        output.seek(0)
        headers = {
            'Content-Disposition': f'attachment; filename="Reporte_Bruto_{quote(semana)}.xlsx"'
        }
        return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/server/ip")
async def get_server_ip():
    """
    Obtiene la IP local del servidor para facilitar el acceso compartido.
    """
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return {"ip": ip, "url": f"http://{ip}:8080"}
    except:
        return {"ip": "127.0.0.1", "url": "http://localhost:8080"}

if __name__ == "__main__":
    db.init_db()
    print("Iniciando servidor FastAPI en http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
