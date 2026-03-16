# Extractor de Órdenes de Movimiento - KPIs de Logística

## 🎯 Objetivo del Proyecto
El objetivo es construir una herramienta interna para el área de logística de una empresa del sector HORECA. Actualmente, el ERP no permite llevar un historial inmutable de los requerimientos originales cuando hay entregas parciales.

Esta aplicación extraerá los datos originales desde los PDFs de las "Órdenes de Movimiento" (generadas por las áreas), los combinará con variables manuales (Semana y Tipo) y los almacenará en una base de datos local para su posterior cruce con los despachos reales (cálculo de KPI de Fill Rate).

---

## 📋 Especificación Técnica Oficial

### 1. Arquitectura Tecnológica (Stack)
- **Lenguaje:** Python 3.9+
- **Frontend:** Streamlit (UI web rápida e interactiva).
- **Base de Datos:** SQLite (ligera, local).
- **Procesamiento de PDF:** `pdfplumber` (para extraer tablas y texto multi-página) y `re` (Expresiones Regulares).
- **Manejo de Datos:** `pandas` (para limpieza y estructuración antes de insertar a BD).

### 2. Modelo de Datos (SQLite)
Se opera con una tabla detallada llamada `requerimientos_originales` en `logistica_kpi.db`.

| Nombre de Columna | Tipo SQLite | Restricciones / Llaves | Descripción |
| :--- | :--- | :--- | :--- |
| **ID_Orden** | INTEGER | **PK Compuesta** | Número de la orden extraído del PDF. |
| **Item** | TEXT | **PK Compuesta** | Nombre exacto del producto (ej. `(I) CAMOTE`). |
| **Almacen_Destino** | TEXT | NOT NULL | Área que solicita (ej. `Cocina Materiales`). |
| **Presentacion** | TEXT | NOT NULL | Unidad de medida (ej. `KILOS`, `UNIDAD`). |
| **Cantidad_Solicitada** | REAL | NOT NULL | Cantidad numérica extraída. |
| **Semana** | TEXT | NOT NULL | Variable de la UI (ej. `Semana 42`). |
| **Tipo_Requerimiento**| TEXT | NOT NULL | `Normal` o `Adicional`. |
| **Fecha_Registro** | TIMESTAMP | DEFAULT NOW() | Fecha/hora de inserción. |

*Nota:* Se utiliza `INSERT OR REPLACE` para evitar duplicación si un usuario vuelve a procesar el mismo PDF.

---

## 🏗️ Estructura del Proyecto

```text
KPI_atencion/
├── .venv/                  # Entorno virtual
├── .gitignore              # Archivos ignorados por Git
├── README.md               # Documentación y Especificación
├── run_app.bat             # Ejecutable rápido para Windows
├── app.py                  # Interfaz de Usuario (Streamlit)
├── requirements.txt       # Dependencias
├── data/                    # Datos persistentes
│   ├── logistica_kpi.db     # Base de Datos (Ignorada por Git)
│   └── ordenes/             # Carpeta para colocar PDFs originales
└── src/                    # Lógica interna y módulos
    ├── __init__.py
    ├── database.py         # Conexión y operaciones SQLite
    ├── extractor.py        # Procesamiento de PDFs
    └── limpiar_db.py       # Script de mantenimiento
```

---

## 📊 Fase Actual
**🟢 Fase 1 - Extracción y Consolidación (Completada)**
- [x] Extracción robusta de tablas multi-página y consolidación.
- [x] Almacenamiento modular ordenado y con trazabilidad.
- [x] Visor de detalles de órdenes integrado en la UI de Streamlit.

---

## 🚀 Cómo Ejecutar

1.  Asegúrate de tener el entorno virtual creado (`.venv`).
2.  Haz doble clic en **`run_app.bat`**.
3.  Ingresa a la URL indicada (usualmente `http://localhost:8501`).
