# Extractor de Órdenes de Movimiento - KPIs de Logística

## 🎯 Objetivo del Proyecto
Esta herramienta permite extraer de forma inmutable los requerimientos originales de las **"Órdenes de Movimiento"** (.pdf) del ERP, para realizar el cruce posterior con los despachos reales y calcular el KPI de **Fill Rate**.

---

## 🏗️ Estructura del Proyecto

```text
KPI_atencion/
├── .venv/                  # Entorno virtual (Local)
├── .gitignore              # Archivos ignorados por Git
├── README.md               # Documentación actual
├── run_app.bat             # Script de ejecución para Windows
├── app.py                  # Interfaz de Usuario (Streamlit)
├── requirements.txt       # Dependencias
└── src/                    # Lógica interna y módulos
    ├── __init__.py
    ├── database.py         # Conexión y operaciones SQLite
    ├── extractor.py        # Procesamiento de PDFs
    └── limpiar_db.py       # Script de mantenimiento
```

---

## 📊 Fase Actual
**🟢 Fase 1 - Extracción y Consolidación (Completada)**
- [x] Lectura de PDFs con Regex y Tablas Multi-página.
- [x] Carga automática a base de datos de forma robusta.
- [x] Visor de historial y métricas en interfaz accesible.

---

## 🚀 Cómo Ejecutar

Para iniciar la aplicación en tu entorno local (Windows):

1.  Asegúrate de tener el entorno virtual creado (`.venv`).
2.  Haz doble clic en **`run_app.bat`**.
3.  Ingresa a la URL indicada (usualmente `http://localhost:8501`).
