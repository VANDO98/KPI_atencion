from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import pandas as pd
import os
import io

import src.database as db
import src.database as db
import src.extractor as ext
from urllib.parse import quote

app = FastAPI(title="KPI Logística API")

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
    
    # Excluir Regularizaciones del cálculo de Fill Rate y KPIs
    if not df_kpi.empty:
        df_kpi = df_kpi[~df_kpi["Tipo_Requerimiento"].isin(["Regularización", "Regularizacion"])]
    
    if df_kpi.empty:
        return {
            "fill_rate_volumen": 0,
            "fill_rate_item": 0,
            "total_items": 0,
            "items_adicionales": 0,
            "fill_rate_adicional": 0,
            "backorders": []
        }
        
    # 1. Fill Rate Global por Volumen
    suma_solicitada = df_kpi["Cantidad_Solicitada"].sum()
    suma_entregada = df_kpi["Cantidad_Entregada"].sum()
    fill_rate_volumen = (suma_entregada / suma_solicitada) * 100 if suma_solicitada > 0 else 0
    
    # 2. Fill Rate Global por Ítem (Promedio Simple)
    fill_rate_item = df_kpi["Fill_Rate_Porcentaje"].mean()
    
    # 3. Datos de Adicionales vs Normales
    df_normales = df_kpi[df_kpi["Tipo_Requerimiento"] == "Normal"]
    df_adicionales = df_kpi[df_kpi["Tipo_Requerimiento"] == "Adicional"]
    items_normales_count = len(df_normales["ID_Orden"].unique())
    items_adicionales_count = len(df_adicionales["ID_Orden"].unique())
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
        "total_items": len(df_kpi),
        "items_adicionales": items_adicionales_count,
        "porcentaje_adicionales": round(porcentaje_adicionales, 2),
        "fill_rate_adicional": round(fill_rate_adicional, 2),
        "pop": round(pop, 2),
        "items_criticos_actual": items_criticos_actual,
        "items_criticos_anterior": items_criticos_anterior,
        "backorders": backorders_json,
        "data_completa": df_kpi.to_dict(orient="records")
    }

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
            reporte.append({
                "Área": area,
                "Fill Rate Global Área": f"{fill_rate_area:.2f}%",
                "Orden": row["ID_Orden"],
                "Tipo": row["Tipo_Requerimiento"],
                "Item": row["Item"],
                "Solicitado": row["Cantidad_Solicitada"],
                "Entregado": row["Cantidad_Entregada"],
                "Pendiente (Deuda)": row["Cantidad_Pendiente"]
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

if __name__ == "__main__":
    db.init_db()
    print("Iniciando servidor FastAPI en http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
