// =========================================
// INICIALIZACIÓN Y VARIABLES
// =========================================
document.addEventListener("DOMContentLoaded", () => {
    // 0. Tema Claro / Oscuro
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) {
        const isLight = localStorage.getItem('light-theme') === 'true';
        if (isLight) {
            document.body.classList.add('light-theme');
            themeBtn.innerHTML = '<i class="fa-solid fa-sun"></i> <span>Modo Claro</span>';
        }

        themeBtn.addEventListener('click', () => {
            document.body.classList.toggle('light-theme');
            const active = document.body.classList.contains('light-theme');
            localStorage.setItem('light-theme', active);
            
            if (active) {
                themeBtn.innerHTML = '<i class="fa-solid fa-sun"></i> <span>Modo Claro</span>';
            } else {
                themeBtn.innerHTML = '<i class="fa-solid fa-moon"></i> <span>Modo Oscuro</span>';
            }
        });
    }

    // 0.1 Sidebar Toggle (Colapsar)
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const appContainer = document.querySelector('.app-container');
    if (sidebarToggle && appContainer) {
        const isCollapsed = localStorage.getItem('sidebar-collapsed') === 'true';
        if (isCollapsed) {
            appContainer.classList.add('collapsed');
        }

        sidebarToggle.addEventListener('click', () => {
            appContainer.classList.toggle('collapsed');
            localStorage.setItem('sidebar-collapsed', appContainer.classList.contains('collapsed'));
        });
    }

    initSemanas();
    loadFilters();
    loadKPIs(); // Carga inicial
    loadOrphanDespachos(); // Cargar los desajustes de nombre si los hay
    setupDragAndDrop();
    initServerInfo();
});

function initSemanas() {
    const selects = ['filtro-semana', 'upload-orden-semana'].map(id => document.getElementById(id));
    for (let i = 1; i <= 53; i++) {
        selects.forEach(sel => {
            if (!sel) return;
            const option = document.createElement('option');
            option.value = `Semana ${i}`;
            option.textContent = `Semana ${i}`;
            sel.appendChild(option);
        });
    }
}

// Cargar filtros dinámicos (Almacenes)
async function loadFilters() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        
        const almacenSelect = document.getElementById('filtro-almacen');
        // Limpiar excepto el primero
        almacenSelect.innerHTML = '<option value="Todos">Todos</option>';
        
        if (data.almacenes) {
            data.almacenes.forEach(alm => {
                const option = document.createElement('option');
                option.value = alm;
                option.textContent = alm;
                almacenSelect.appendChild(option);
            });
        }

        // [NUEVO] Seleccionar automáticamente la última semana cargada
        if (data.last_semana) {
            const uploadWeekSelect = document.getElementById('upload-orden-semana');
            if (uploadWeekSelect) {
                uploadWeekSelect.value = data.last_semana;
            }
        }
    } catch (err) {
        console.error("Error cargando filtros:", err);
    }
}

// =========================================
// CARGA DE KPIS (DASHBOARD)
// =========================================
async function loadKPIs() {
    const semana = document.getElementById('filtro-semana').value;
    const almacen = document.getElementById('filtro-almacen').value;
    const tipo = document.getElementById('filtro-tipo').value;
    
    let url = `/api/kpi?semana=${encodeURIComponent(semana)}&almacen=${encodeURIComponent(almacen)}&tipo=${encodeURIComponent(tipo)}`;
    
    try {
        const res = await fetch(url);
        const data = await res.json();
        
        // Actualizar Tarjetas
        document.getElementById('val-volumen').textContent = `${data.fill_rate_volumen}%`;
        document.getElementById('val-item').textContent = `${data.fill_rate_item}%`;
        document.getElementById('val-adicional').textContent = `${data.porcentaje_adicionales}%`;
        document.getElementById('sub-adicional').textContent = `vs Normales (${data.items_adicionales} ítems)`;
        
        // --- [NUEVO] Renderizar Tarjeta Financiera ---
        const finEl = document.getElementById('val-financiero');
        if (finEl) finEl.textContent = `${data.fill_rate_financiero}%`;
        
        const subFinEl = document.getElementById('sub-financiero');
        if (subFinEl) {
            subFinEl.textContent = `S/ ${data.monto_entregado.toLocaleString('es-PE', {minimumFractionDigits: 2})} / S/ ${data.monto_solicitado.toLocaleString('es-PE', {minimumFractionDigits: 2})}`;
        }
        
        const popEl = document.getElementById('val-pop');
        if (popEl) popEl.textContent = `${data.pop}%`;
        
        // --- [NUEVO] Renderizar Tarjeta Regularizaciones ---
        const regEl = document.getElementById('val-regularizaciones');
        if (regEl) regEl.textContent = `${data.porcentaje_regularizacion}%`;
        

        // Renderizar Tabla Backorders
        const tbody = document.querySelector('#tabla-backorders tbody');
        tbody.innerHTML = '';
        
        if (data.backorders && data.backorders.length > 0) {
            // 1. Agrupar por Almacén (Área) -> ID_Orden
            const grouped = {};
            data.backorders.forEach(b => {
                const area = b.Almacen_Destino || "Sin Área";
                if (!grouped[area]) grouped[area] = {};
                
                const id_orden = b.ID_Orden;
                if (!grouped[area][id_orden]) {
                    grouped[area][id_orden] = {
                        tipo: b.Tipo_Requerimiento || "Normal",
                        items: []
                    };
                }
                grouped[area][id_orden].items.push(b);
            });
            
            // 2. Renderizar Grupos
            let areaIndex = 0;
            for (const [area, ordenes] of Object.entries(grouped)) {
                areaIndex++;
                const currentAreaIndex = areaIndex;
                
                // Cabecera Area
                const trArea = document.createElement('tr');
                trArea.style.background = "rgba(0, 242, 254, 0.08)";
                trArea.style.cursor = "pointer";
                
                const totalItems = Object.values(ordenes).reduce((sum, o) => sum + o.items.length, 0);
                // NOTA: Se añade onclick para togglear
                trArea.innerHTML = `
                    <td colspan="9" style="font-weight: 800; color: var(--accent); padding: 12px 15px;" onclick="toggleArea('${currentAreaIndex}')">
                        <i class="fa-solid fa-chevron-down" id="arrow-area-${currentAreaIndex}" style="margin-right: 8px; transition: transform 0.2s;"></i>
                        Área: ${area} 
                        <span style="font-size: 12px; color: var(--text-secondary); font-weight: 400;">(${totalItems} ítems faltantes - Clic para colapsar)</span>
                    </td>
                `;
                tbody.appendChild(trArea);
                
                for (const [id_orden, orden_data] of Object.entries(ordenes)) {
                    const trOrden = document.createElement('tr');
                    trOrden.className = `area-row-${currentAreaIndex}`;
                    trOrden.style.background = "rgba(255, 255, 255, 0.03)";
                    
                    const selectHtml = `
                        <select class="select-tipo" data-id="${id_orden}" onclick="event.stopPropagation()" style="background: #1a1f26; color: #ffffff; border: 1px solid rgba(0, 242, 254, 0.4); padding: 5px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; font-weight: 500;">
                            <option value="Normal" ${orden_data.tipo === 'Normal' ? 'selected' : ''}>Normal</option>
                            <option value="Adicional" ${orden_data.tipo === 'Adicional' ? 'selected' : ''}>Adicional</option>
                            <option value="Regularización" ${orden_data.tipo === 'Regularización' || orden_data.tipo === 'Regularizacion' ? 'selected' : ''}>Regularización</option>
                        </select>
                    `;
                    
                    // Se añade onclick para expandir/colapsar la orden
                    trOrden.innerHTML = `
                        <td colspan="9" style="padding-left: 30px; font-weight: 600; color: var(--text-primary); cursor: pointer;" onclick="toggleOrden('${id_orden}')">
                            <i class="fa-solid fa-chevron-right" id="arrow-orden-${id_orden}" style="margin-right: 8px; transition: transform 0.2s;"></i>
                            <i class="fa-solid fa-file-invoice"></i> Orden #${id_orden} 
                            <span style="margin-left: 20px; font-weight: 400; color: var(--text-secondary);">Tipo:</span> ${selectHtml}
                        </td>
                    `;
                    tbody.appendChild(trOrden);
                    
                    orden_data.items.forEach(b => {
                        const tr = document.createElement('tr');
                        // Hereda del area y pertenece a la orden. COMLAPSADO POR DEFECTO.
                        tr.className = `area-row-${currentAreaIndex} orden-items-${id_orden}`;
                        tr.style.display = 'none'; 
                        tr.innerHTML = `
                            <td style="padding-left: 45px; font-size: 12px; color: var(--text-secondary);">${b.ID_Orden}</td>
                            <td>${b.Item}</td>
                            <td>${b.Almacen_Destino}</td>
                            <td>${b.Cantidad_Solicitada}</td>
                            <td>${b.Cantidad_Entregada}</td>
                            <td style="color: var(--danger); font-weight: 800;">${b.Cantidad_Pendiente}</td>
                            <td>S/ ${b.Costo ? b.Costo.toFixed(2) : '0.00'}</td>
                            <td style="font-weight: 800; color: #ff5252;">S/ ${b.Costo ? (b.Cantidad_Pendiente * b.Costo).toFixed(2) : '0.00'}</td>
                            <td style="text-align: center;">
                                <button class="btn btn-primary" style="padding: 3px 6px; font-size: 11px; background-color: var(--success); border-color: var(--success);" onclick="forzarCumplimiento(this, ${b.ID_Orden}, '${b.Item.replace(/'/g, "\\'")}')" title="Forzar 100%">
                                    ✔ Forzar
                                </button>
                            </td>
                        `;
                        tbody.appendChild(tr);
                    });
                }
            }
            
            // 3. Vincular Eventos
            document.querySelectorAll('.select-tipo').forEach(sel => {
                sel.addEventListener('change', async (e) => {
                    const id = e.target.getAttribute('data-id');
                    const nuevo_tipo = e.target.value;
                    await actualizarTipoOrden(id, nuevo_tipo);
                });
            });
            
        } else {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--success); font-weight: 800; padding: 20px;">🎉 ¡No hay Backorders! Todo lo solicitado fue entregado.</td></tr>';
        }

        // 4. Renderizar Items Críticos Actual vs Anterior
        const tbodyCriticos = document.querySelector('#tabla-items-criticos tbody');
        if (tbodyCriticos) {
            tbodyCriticos.innerHTML = '';
            const actual = data.items_criticos_actual || [];
            const anterior = data.items_criticos_anterior || [];
            
            if (actual.length > 0) {
                actual.forEach(item_act => {
                    const item_ant = anterior.find(i => i.Item === item_act.Item);
                    const deuda_ant = item_ant ? item_ant.Cantidad_Pendiente : '0';
                    const es_repetitivo = item_ant && item_ant.Cantidad_Pendiente > 0;
                    
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${item_act.Item}</strong></td>
                        <td style="color: var(--danger); font-weight: 800;">${item_act.Cantidad_Pendiente}</td>
                        <td style="color: var(--text-secondary);">${deuda_ant}</td>
                        <td>${es_repetitivo ? '<span style="background: rgba(220, 53, 69, 0.2); color: #ff4d4d; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 800;"><i class="fa-solid fa-triangle-exclamation"></i> REPETITIVO</span>' : '<span style="color: var(--success);">Novedad</span>'}</td>
                    `;
                    tbodyCriticos.appendChild(tr);
                });
            } else {
                tbodyCriticos.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 15px; color: var(--success);">🎉 No hay items críticos con deuda.</td></tr>';
            }
        }
        
        // [NUEVO] Cargar o recargar la tabla de desajustes basados en los filtros actuales
        loadOrphanDespachos();

    } catch (err) {
        console.error("Error cargando KPIs:", err);
    }
}

// =========================================
// NAVEGACIÓN Y CARGA DE ARCHIVOS
// =========================================
function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(t => t.classList.remove('active'));
    
    document.getElementById('tab-' + tabId).classList.add('active');
    // Asegurar que se activa el botón que disparó el evento
    event.currentTarget.classList.add('active');
    
    if (tabId === 'dashboard') {
        loadFilters();
        loadKPIs();
    } else if (tabId === 'gestor-ordenes') {
        loadGestorOrdenes();
    } else if (tabId === 'reportes-analiticos') {
        loadReportsSummary();
    }
}

// Memoria global para los archivos seleccionados
const uploadedFiles = { orden: [], despacho: [] };

// Arrastrar y Soltar (Drag & Drop)
function setupDragAndDrop() {
    const zones = ['orden', 'despacho'];
    
    zones.forEach(zone => {
        const dropZone = document.getElementById(`drop-zone-${zone}`);
        const input = document.getElementById(`input-${zone}`);
        
        if (!dropZone || !input) return;

        dropZone.addEventListener('click', () => input.click());
        
        // Evitar comportamiento por defecto que bloquea el drop
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                if (eventName === 'dragover') dropZone.classList.add('dragover');
            });
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            // Guardar en memoria global
            uploadedFiles[zone] = Array.from(e.dataTransfer.files);
            updateDropZoneLabel(dropZone, uploadedFiles[zone], zone);
        });

        input.addEventListener('change', () => {
            uploadedFiles[zone] = Array.from(input.files);
            updateDropZoneLabel(dropZone, uploadedFiles[zone], zone);
        });
    });
}

function updateDropZoneLabel(dropZone, files, tipo) {
    if (files.length > 0) {
        dropZone.innerHTML = `<i class="fa-solid fa-file-circle-check" style="color: var(--success)"></i><p>${files.length} archivo(s) seleccionado(s)</p>`;
    } else {
        dropZone.innerHTML = `<i class="fa-solid fa-file-${tipo === 'orden' ? 'pdf' : 'invoice'}"></i><p>Arrastra PDF aquí</p>`;
    }
}

// Subir PDF a la API
async function uploadPDF(tipo) {
    const files = uploadedFiles[tipo];
    if (!files || files.length === 0) {
        alert("⚠️ Selecciona al menos un archivo PDF.");
        return;
    }

    const formData = new FormData();
    // Añadir todos los archivos con la clave "files" para coincidir con el backend
    for (let i = 0; i < files.length; i++) {
        formData.append("files", files[i]);
    }

    let url = `/api/upload/${tipo}`;
    if (tipo === 'orden') {
        const semana = document.getElementById('upload-orden-semana').value;
        const tipoReq = document.querySelector('input[name="tipo_req"]:checked').value;
        url += `?semana=${encodeURIComponent(semana)}&tipo_requerimiento=${encodeURIComponent(tipoReq)}`;
    }

    try {
        const btn = event.target;
        btn.innerText = "⏳ Procesando...";
        btn.disabled = true;

        const res = await fetch(url, {
            method: 'POST',
            body: formData
        });

        const result = await res.json();
        
        if (res.ok) {
            alert(`✅ ¡Éxito! ${result.message}`);
            // Limpiar memoria
            uploadedFiles[tipo] = [];
            const dropZone = document.getElementById(`drop-zone-${tipo}`);
            updateDropZoneLabel(dropZone, [], tipo);
            const input = document.getElementById(`input-${tipo}`);
            if (input) input.value = "";
            
            // --- ACTUALIZACIÓN AUTOMÁTICA DEL DASHBOARD ---
            loadKPIs(); 
            if (typeof loadGestorOrdenes === 'function') loadGestorOrdenes();
        } else {
            alert(`❌ Error: ${result.error || result.detail || JSON.stringify(result.errores)}`);
        }
    } catch (err) {
        console.error(`Error subiendo ${tipo}:`, err);
        alert("❌ Error de red o servidor.");
    } finally {
        document.querySelectorAll('.btn-primary').forEach(b => {
             b.innerText = `🚀 Procesar ${tipo === 'orden' ? 'Órdenes' : 'Despachos'}`;
             b.disabled = false;
        });
    }
}

async function actualizarTipoOrden(id_orden, nuevo_tipo) {
    try {
        const res = await fetch('/api/orden/update_tipo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id_orden: parseInt(id_orden), nuevo_tipo: nuevo_tipo })
        });
        const data = await res.json();
        if (data.success) {
            loadKPIs(); 
        } else {
            alert("Error: " + data.message);
        }
    } catch (err) {
        console.error(err);
    }
}

async function loadGestorOrdenes() {
    const tbody = document.querySelector('#tabla-gestor-ordenes tbody');
    try {
        const res = await fetch('/api/ordenes');
        const data = await res.json();
        
        tbody.innerHTML = '';
        
        // Diagnóstico: Si respuesta no es un array (ej. error 500 con dict)
        if (!Array.isArray(data)) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 20px; color: var(--danger);">❌ Error del servidor: ${data.detail || JSON.stringify(data)}</td></tr>`;
            return;
        }
        
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 20px; color: var(--text-secondary);">No hay órdenes cargadas.</td></tr>';
            return;
        }
        
        data.forEach(ord => {
            const tr = document.createElement('tr');
            
            let semanaOptions = '';
            for (let i = 1; i <= 53; i++) {
                const weekText = `Semana ${i}`;
                semanaOptions += `<option value="${weekText}" ${ord.Semana === weekText ? 'selected' : ''}>${weekText}</option>`;
            }
            
            const selectSemana = `
                <select class="gestor-semana" data-id="${ord.ID_Orden}" style="background: #1a1f26; color: #fff; border: 1px solid rgba(255,255,255,0.1); padding: 5px; border-radius: 4px; font-size: 13px;">
                    ${semanaOptions}
                </select>
            `;
            
            const selectTipo = `
                <select class="gestor-tipo" data-id="${ord.ID_Orden}" style="background: #1a1f26; color: #fff; border: 1px solid rgba(255,255,255,0.1); padding: 5px; border-radius: 4px; font-size: 13px;">
                    <option value="Normal" ${ord.Tipo_Requerimiento === 'Normal' ? 'selected' : ''}>Normal</option>
                    <option value="Adicional" ${ord.Tipo_Requerimiento === 'Adicional' ? 'selected' : ''}>Adicional</option>
                    <option value="Regularización" ${ord.Tipo_Requerimiento === 'Regularización' || ord.Tipo_Requerimiento === 'Regularizacion' ? 'selected' : ''}>Regularización</option>
                </select>
            `;
            
            tr.innerHTML = `
                <td style="font-weight: 800; color: var(--accent);">#${ord.ID_Orden}</td>
                <td>${selectSemana}</td>
                <td>${selectTipo}</td>
                <td style="text-align: center; display: flex; gap: 10px; justify-content: center;">
                    <button class="btn-icon" onclick="verDetalleOrden(${ord.ID_Orden})" title="Ver Detalles">
                        <i class="fa-solid fa-eye"></i>
                    </button>
                    <button class="btn-primary" onclick="guardarCambiosOrden(${ord.ID_Orden})" style="padding: 6px 12px; font-size: 12px; font-weight: 800; background: var(--accent); color: #0b0f15; border: none; border-radius: 4px; cursor: pointer; flex: 1; max-width: 100px;">💾 Guardar</button>
                    <button class="btn-icon" onclick="eliminarOrden(${ord.ID_Orden})" title="Eliminar Orden" style="color: #f44336; border-color: rgba(244, 67, 54, 0.2); background: rgba(244, 67, 54, 0.05);">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error en Gestor de Órdenes:", err);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 20px; color: var(--danger);">❌ Error de JS: ${err.message}</td></tr>`;
        }
    }
}

async function eliminarOrden(id_orden) {
    if (!confirm(`⚠️ ¿Estás totalmente seguro de que deseas ELIMINAR la Orden #${id_orden}?\nEsta acción no se puede deshacer y borrará todos los requerimientos vinculados a esta orden, pudiendo afectar las métricas de Fill Rate si ya existen despachos cargados.`)) {
        return;
    }
    
    try {
        const res = await fetch(`/api/ordenes/${id_orden}`, { method: 'DELETE' });
        const data = await res.json();
        
        if (data.success) {
            alert(`✅ ${data.message}`);
            // Recargar tabla de gestor
            loadGestorOrdenes();
            // Actualizar filtros por si la semana se quedó vacía
            loadFilters();
            loadKPIs();
        } else {
            alert(`❌ Error al eliminar: ${data.message}`);
        }
    } catch (err) {
        console.error("Error eliminando orden:", err);
        alert("Ocurrió un error inesperado al contactar con el servidor. Revisa la consola.");
    }
}

// =========================================
// MODAL DETALLE DE ORDEN
// =========================================

async function verDetalleOrden(id_orden) {
    const modal = document.getElementById('modal-detalle-orden');
    const titulo = document.getElementById('modal-orden-titulo');
    const tbody = document.querySelector('#tabla-modal-orden tbody');
    
    // Preparar UI
    titulo.innerHTML = `<i class="fa-solid fa-box-open"></i> Detalles de la Orden #${id_orden}`;
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">⏳ Cargando ítems...</td></tr>';
    modal.classList.add('active');
    
    try {
        const res = await fetch(`/api/orden/${id_orden}/items`);
        const data = await res.json();
        
        if (data.success && data.items.length > 0) {
            tbody.innerHTML = '';
            let totalDeuda = 0;
            
            data.items.forEach(item => {
                const tr = document.createElement('tr');
                const p = item.Pend;
                const req = item.Soli;
                const ent = item.Entr;
                const valorDeuda = p > 0 ? (p * item.Valor_Unitario) : 0;
                totalDeuda += valorDeuda;
                
                let textColor = 'var(--text-secondary)';
                if (p > 0) textColor = 'var(--danger)'; 
                else if (p < 0) textColor = 'var(--warning)';
                else textColor = 'var(--success)';
                
                tr.innerHTML = `
                    <td style="font-weight: 600;">${item.Item}</td>
                    <td style="font-size: 11px;">${item.Almacen}</td>
                    <td>S/ ${item.Valor_Unitario.toFixed(2)}</td>
                    <td>${req}</td>
                    <td>${ent}</td>
                    <td style="color: ${textColor}; font-weight: 800;">
                        ${p}
                        ${p > 0 ? `<br><span style="font-size: 10px;">(S/ ${valorDeuda.toFixed(2)})</span>` : ''}
                    </td>
                `;
                tbody.appendChild(tr);
            });
            
            // Fila de resumen de deuda
            if (totalDeuda > 0) {
                const trResumen = document.createElement('tr');
                trResumen.style.background = 'rgba(255, 0, 0, 0.05)';
                trResumen.innerHTML = `
                    <td colspan="5" style="text-align: right; font-weight: 800; color: var(--text-primary);">Deuda Total a Valorizar:</td>
                    <td style="font-weight: 800; color: var(--danger);">S/ ${totalDeuda.toFixed(2)}</td>
                `;
                tbody.appendChild(trResumen);
            }
            
        } else {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--warning);">⚠️ No se encontraron ítems para esta orden.</td></tr>';
        }
    } catch (err) {
        console.error("Error cargando detalle de orden:", err);
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--danger);">❌ Error de conexión al servidor.</td></tr>`;
    }
}

function cerrarModalOrden() {
    document.getElementById('modal-detalle-orden').classList.remove('active');
}

// Cierre al hacer click fuera
document.getElementById('modal-detalle-orden').addEventListener('click', function(e) {
    if (e.target === this) cerrarModalOrden();
});

function filtrarOrdenesGestor() {
    const input = document.getElementById('buscar-orden-gestor').value.toLowerCase().trim();
    const rows = document.querySelectorAll('#tabla-gestor-ordenes tbody tr');
    
    rows.forEach(row => {
        const idCell = row.cells[0]; // Primera columna (#1639)
        if (idCell) {
            const idText = idCell.textContent.replace('#', '').trim().toLowerCase();
            // Soporta búsqueda parcial (ej. "16" encuentra 1639)
            if (idText.includes(input) || input === '') {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        }
    });
}

async function guardarCambiosOrden(id_orden) {
    const row = document.querySelector(`.gestor-semana[data-id="${id_orden}"]`).closest('tr');
    const semana = row.querySelector('.gestor-semana').value;
    const tipo = row.querySelector('.gestor-tipo').value;
    
    try {
        const res = await fetch('/api/orden/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id_orden: id_orden, semana: semana, tipo: tipo })
        });
        const data = await res.json();
        if (data.success) {
            alert(`✅ ¡Éxito! Orden #${id_orden} actualizada.`);
            loadGestorOrdenes(); 
        } else {
            alert(`❌ Error: ${data.message}`);
        }
    } catch (err) {
        alert("❌ Error de red.");
    }
}

function toggleArea(index) {
    const rows = document.querySelectorAll(`.area-row-${index}`);
    const arrow = document.getElementById(`arrow-area-${index}`);
    if (!rows || rows.length === 0) return;
    
    const isCollapsed = rows[0].style.display === 'none';
    rows.forEach(r => {
        r.style.display = isCollapsed ? '' : 'none';
    });
    if (arrow) {
        arrow.style.transform = isCollapsed ? 'rotate(0deg)' : 'rotate(-90deg)';
    }
}

function toggleOrden(id_orden) {
    const rows = document.querySelectorAll(`.orden-items-${id_orden}`);
    const arrow = document.getElementById(`arrow-orden-${id_orden}`);
    if (!rows || rows.length === 0) return;
    
    const isCollapsed = rows[0].style.display === 'none';
    rows.forEach(r => {
        r.style.display = isCollapsed ? '' : 'none';
    });
    if (arrow) {
        arrow.style.transform = isCollapsed ? 'rotate(90deg)' : 'rotate(0deg)';
    }
}

async function descargarReporteExcel() {
    const semana = document.getElementById('filtro-semana').value;
    const btn = document.getElementById('btn-export-excel');
    const originalText = btn.innerHTML;
    
    try {
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando...';
        btn.style.opacity = '0.7';
        btn.disabled = true;
        
        const res = await fetch(`/api/report/excel?semana=${encodeURIComponent(semana)}`);
        
        if (!res.ok) {
            const err = await res.json();
            alert(`⚠️ ${err.detail || 'Error al generar reporte'}`);
            return;
        }
        
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Reporte_NoAtendidos_${semana.replace(/\s+/g, '_')}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    } catch (err) {
        alert("❌ Error de red al descargar el reporte.");
    } finally {
        btn.innerHTML = originalText;
        btn.style.opacity = '1';
        btn.disabled = false;
    }
}

async function descargarReporteAdicionales() {
    const semana = document.getElementById('filtro-semana').value;
    const btn = document.getElementById('btn-export-excel-adicionales');
    const originalText = btn.innerHTML;
    
    try {
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando...';
        btn.style.opacity = '0.7';
        btn.disabled = true;
        
        const res = await fetch(`/api/report/adicionales/excel?semana=${encodeURIComponent(semana)}`);
        
        if (!res.ok) {
            const err = await res.json();
            alert(`⚠️ ${err.detail || 'Error al generar reporte'}`);
            return;
        }
        
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Reporte_Adicionales_${semana.replace(/\s+/g, '_')}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    } catch (err) {
        alert("❌ Error de red al descargar el reporte.");
    } finally {
        btn.innerHTML = originalText;
        btn.style.opacity = '1';
        btn.disabled = false;
    }
}

// =========================================
// GESTOR DE DESPACHOS [NUEVO]
// =========================================
async function loadOrphanDespachos() {
    try {
        const semana = document.getElementById('filtro-semana')?.value || 'Todas';
        const almacen = document.getElementById('filtro-almacen')?.value || 'Todos';
        const res = await fetch(`/api/despachos/huerfanos?semana=${encodeURIComponent(semana)}&almacen=${encodeURIComponent(almacen)}`);
        const data = await res.json();

        // 1. Renderizar Fantasmas
        const tbodyFantasmas = document.querySelector('#tabla-fantasmas tbody');
        if (tbodyFantasmas) {
            tbodyFantasmas.innerHTML = '';
            if (data.fantasmas && data.fantasmas.length > 0) {
                data.fantasmas.forEach(d => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${d.ID_Movimiento}</td>
                        <td><span class="badge" style="background: rgba(244, 67, 54, 0.15); color: #f44336; border: 1px solid #f44336; padding: 2px 6px; borderRadius: 4px;"># ${d.ID_Orden_Ref}</span></td>
                        <td>${d.Item}</td>
                        <td>${d.Cantidad_Entregada}</td>
                        <td>${d.Fecha_Registro ? d.Fecha_Registro.substring(0,10) : '-'}</td>
                    `;
                    tbodyFantasmas.appendChild(tr);
                });
            } else {
                tbodyFantasmas.innerHTML = '<tr><td colspan="5" style="text-align:center; color: #888;">🎉 ¡Cero huérfanos! Todo en orden.</td></tr>';
            }
        }

        // 2. Renderizar Desajustes de Nombre y Ocultarla si está vacía en el Dashboard
        const tbodyDesajustes = document.querySelector('#tabla-desajustes tbody');
        const cardDesajustes = document.getElementById('card-desajustes-dashboard');
        
        if (tbodyDesajustes) {
            tbodyDesajustes.innerHTML = '';
            if (data.desajustes_nombre && data.desajustes_nombre.length > 0) {
                if (cardDesajustes) cardDesajustes.style.display = 'block';
                
                data.desajustes_nombre.forEach(d => {
                    const tr = document.createElement('tr');
                    
                    let optionsHtml = '<option value="">-- Seleccione el Ítem Correcto --</option>';
                    if (d.Opciones_Items) {
                        d.Opciones_Items.forEach(opt => {
                            optionsHtml += `<option value="${opt.replace(/"/g, '&quot;')}">${opt}</option>`;
                        });
                    }

                    tr.innerHTML = `
                        <td>${d.ID_Movimiento}</td>
                        <td><span class="badge" style="background: rgba(255, 152, 0, 0.15); color: #ff9800; border: 1px solid #ff9800; padding: 2px 6px; borderRadius: 4px;"># ${d.ID_Orden_Ref}</span></td>
                        <td>
                            <div style="color: #f44336; font-weight: 500;">${d.Item}</div>
                            <div style="font-size:11px; color:#888;">(Ítem físico ingresado)</div>
                        </td>
                        <td>${d.Cantidad_Entregada}</td>
                        <td>${d.Fecha_Registro ? d.Fecha_Registro.substring(0,10) : '-'}</td>
                        <td style="text-align: center; display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <select class="input-modern" id="select-correccion-${d.ID_Movimiento}" style="max-width: 160px; font-size: 11px; padding: 4px;">
                                ${optionsHtml}
                            </select>
                            <button class="btn btn-primary" style="padding: 4px 8px; font-size: 11px;" onclick="corregirDespacho(${d.ID_Movimiento}, '${d.Item.replace(/'/g, "\\'")}')">
                                <i class="fa-solid fa-link"></i> Vincular
                            </button>
                        </td>
                    `;
                    tbodyDesajustes.appendChild(tr);
                });
            } else {
                tbodyDesajustes.innerHTML = '<tr><td colspan="6" style="text-align:center; color: #888;">🎉 Sin desajustes de nombre actual.</td></tr>';
                if (cardDesajustes) cardDesajustes.style.display = 'none'; // Ocultar si está limpio
            }
        }

    } catch (err) {
        console.error("Error cargando despachos huérfanos:", err);
    }
}

async function corregirDespacho(id_movimiento, item_original) {
    const select = document.getElementById(`select-correccion-${id_movimiento}`);
    if (!select) return;
    const item_nuevo = select.value;
    
    if (!item_nuevo) {
        alert("Por favor, selecciona un ítem válido de la lista desplegable.");
        return;
    }
    
    try {
        const res = await fetch('/api/despacho/corregir_item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id_movimiento: id_movimiento,
                item_original: item_original,
                item_nuevo: item_nuevo
            })
        });
        const data = await res.json();
        if (data.success) {
            alert(`✅ ¡Ítem vinculado correctamente!`);
            loadOrphanDespachos(); // Recargar tabla de huérfanos
            loadKPIs(); // Recargar KPIs en background
            const gestorTab = document.getElementById('tab-gestor-ordenes');
            if (gestorTab && gestorTab.classList.contains('active')) {
                 if (typeof loadGestorOrdenes === 'function') loadGestorOrdenes();
            }
        } else {
            alert(`❌ Error DB: ${data.message || JSON.stringify(data)}`);
        }
    } catch (err) {
        alert(`❌ Error Interno JS: ${err.message}\nVerifica consola del navegador (F12)`);
    }
}

// =========================================
// ACCIONES DE CUMPLIMIENTO (NUEVO)
// =========================================
async function forzarCumplimiento(btn, id_orden, item_original) {
    if (!confirm(`⚠️ Vas a marcar el ítem "${item_original}" de la Orden #${id_orden} como ENTREGADO AL 100% de forma manual.\n\nEl sistema asume que la diferencia fue un tema de unidades o presentación y cerrará esta deuda asumiendo que entregaste la misma cantidad solicitada.\n\n¿Estás seguro de forzar el cumplimiento?`)) {
        return;
    }
    
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    btn.disabled = true;

    try {
        const res = await fetch('/api/orden/forzar_cumplimiento', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id_orden: id_orden,
                item: item_original
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            // Eliminamos la fila local del navegador sin recargar nada
            const tr = btn.closest('tr');
            if (tr) tr.remove();
            
            // Recargamos silenciosamente los contadores numéricos de arriba, pero SIN redibujar la tabla
            loadMetricasBaseSilencioso();
        } else {
            alert(`❌ Error DB: ${data.message || JSON.stringify(data)}`);
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        }
    } catch (err) {
        alert(`❌ Error Interno JS: ${err.message}\nVerifica consola del navegador (F12)`);
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    }
}

async function loadMetricasBaseSilencioso() {
    try {
        const semana = document.getElementById('filtro-semana').value;
        const almacen = document.getElementById('filtro-almacen').value;
        const res = await fetch(`/api/kpi?semana=${encodeURIComponent(semana)}&almacen=${encodeURIComponent(almacen)}&tipo=Todos`);
        const data = await res.json();
        
        document.getElementById('metric-fillrate').innerText = data.metricas.fill_rate + '%';
        document.getElementById('metric-deuda').innerText = 'S/ ' + data.metricas.deuda_total.toFixed(2);
        document.getElementById('metric-pendientes').innerText = data.metricas.ítems_pendientes;
        document.getElementById('metric-ordenes').innerText = data.metricas.órdenes_atendidas;
    } catch(err) {
        console.error("Error al refrescar las tarjetas", err);
    }
}

// Función genérica para cambiar de pestaña activa [NUEVO / COMPLEMENTO]
function switchTab(tabId) {
    const tabs = document.querySelectorAll('.tab-content');
    const navItems = document.querySelectorAll('.nav-item');

    tabs.forEach(tab => {
        tab.classList.remove('active');
    });

    navItems.forEach(item => {
        item.classList.remove('active');
        // Activar el que corresponde por onclick
        if (item.getAttribute('onclick') && item.getAttribute('onclick').includes(tabId)) {
            item.classList.add('active');
        }
    });

    const activeTab = document.getElementById(`tab-${tabId}`);
    if (activeTab) {
         activeTab.classList.add('active');
    }

    // Cursos de carga para tabs específicas
    if (tabId === 'gestor-despachos') {
        loadOrphanDespachos();
    } else if (tabId === 'gestor-ordenes') {
         if (typeof loadGestorOrdenes === 'function') loadGestorOrdenes();
    } else if (tabId === 'dashboard') {
        loadFilters();
        loadKPIs();
    } else if (tabId === 'reportes-analiticos') {
        loadReportsSummary();
    }
}

// =========================================
// REPORTES ANALÍTICOS [NUEVO]
// =========================================
let chartTrend = null;
let chartType = null;

async function loadReportsSummary() {
    try {
        const res = await fetch('/api/reports/summary');
        const data = await res.json();
        
        renderReportTables(data);
        renderReportCharts(data);
    } catch (err) {
        console.error("Error al cargar reportes:", err);
    }
}

function renderReportTables(data) {
    const tbodySemana = document.querySelector('#tabla-reporte-semanal tbody');
    const tbodyAlmacen = document.querySelector('#tabla-reporte-almacen tbody');
    
    if (tbodySemana) {
        tbodySemana.innerHTML = '';
        if (!data.semanas || data.semanas.length === 0) {
            tbodySemana.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 20px;">⚠️ No hay datos registrados para mostrar reportes.</td></tr>';
        } else {
            data.semanas.forEach(s => {
                const tr = document.createElement('tr');
                const fr = (s.Fill_Rate_Porcentaje || 0).toFixed(2);
                let statusClass = fr > 90 ? 'var(--success)' : (fr > 70 ? 'var(--warning)' : 'var(--danger)');
                
                tr.innerHTML = `
                    <td style="font-weight: 800; color: var(--accent);">${s.Semana}</td>
                    <td>${s.ID_Orden}</td>
                    <td>${s.Item}</td>
                    <td>${(s.Cantidad_Solicitada || 0).toLocaleString()}</td>
                    <td>${(s.Cantidad_Entregada || 0).toLocaleString()}</td>
                    <td style="font-weight: 800; color: ${statusClass}">${fr}%</td>
                    <td><span style="background: ${statusClass}22; color: ${statusClass}; padding: 3px 8px; border-radius: 4px; font-size: 11px;">${fr > 85 ? 'Óptimo' : 'Bajo'}</span></td>
                    <td style="text-align: center;">
                        <button class="btn btn-primary" style="padding: 5px 10px; font-size: 11px; background: #5aeb8c; color: #0b0f15; border: none;" onclick="descargarReporteBruto('${s.Semana}')">
                            <i class="fa-solid fa-file-excel"></i> Excel
                        </button>
                    </td>
                `;
                tbodySemana.appendChild(tr);
            });
        }
    }

    if (tbodyAlmacen) {
        tbodyAlmacen.innerHTML = '';
        if (!data.almacenes || data.almacenes.length === 0) {
            tbodyAlmacen.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 20px;">- Sin datos de almacén -</td></tr>';
        } else {
            data.almacenes.forEach(a => {
                const tr = document.createElement('tr');
                const fr = (a.Fill_Rate_Porcentaje || 0).toFixed(2);
                let statusColor = fr > 90 ? '#10b981' : (fr > 75 ? '#f59e0b' : '#ef4444');
                
                tr.innerHTML = `
                    <td style="font-weight: 600;">${a.Almacen_Destino}</td>
                    <td>${a.ID_Orden} órdenes</td>
                    <td style="font-weight: 800; color: ${statusColor}">${fr}%</td>
                    <td>
                        <div style="width: 100%; height: 8px; background: rgba(255,255,255,0.05); border-radius: 10px; overflow: hidden; border: 1px solid rgba(255,255,255,0.05);">
                            <div style="width: ${fr}%; height: 100%; background: linear-gradient(90deg, ${statusColor}cc, ${statusColor}); box-shadow: 0 0 10px ${statusColor}44;"></div>
                        </div>
                    </td>
                `;
                tbodyAlmacen.appendChild(tr);
            });
        }
    }
}

async function descargarReporteBruto(semana) {
    try {
        const btn = event.target;
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
        btn.disabled = true;

        const res = await fetch(`/api/report/raw/excel?semana=${encodeURIComponent(semana)}`);
        
        if (!res.ok) {
            const err = await res.json();
            alert(`⚠️ ${err.detail || 'Error al generar reporte'}`);
            return;
        }
        
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Reporte_Bruto_${semana.replace(/\s+/g, '_')}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    } catch (err) {
        alert("❌ Error de red al descargar el reporte.");
    } finally {
        const btns = document.querySelectorAll('.btn');
        btns.forEach(b => {
            if (b.innerText.includes('Excel') || b.innerHTML.includes('fa-file-excel')) {
                b.disabled = false;
                b.innerHTML = '<i class="fa-solid fa-file-excel"></i> Excel';
            }
        });
    }
}

function renderReportCharts(data) {
    const canvasTrend = document.getElementById('chart-tendencia-fr');
    const canvasType = document.getElementById('chart-distribucion-tipo');
    
    if (!canvasTrend || !canvasType) return;

    // Destruir instancias previas si existen
    if (chartTrend) chartTrend.destroy();
    if (chartType) chartType.destroy();

    // 1. Gráfico de Tendencia (Line)
    const labelsTrend = data.semanas.map(s => s.Semana);
    const dataTrend = data.semanas.map(s => s.Fill_Rate_Porcentaje);

    chartTrend = new Chart(canvasTrend, {
        type: 'line',
        data: {
            labels: labelsTrend,
            datasets: [{
                label: 'Fill Rate % Promedio',
                data: dataTrend,
                borderColor: '#00f2fe',
                backgroundColor: 'rgba(0, 242, 254, 0.1)',
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#00f2fe',
                pointBorderColor: '#fff',
                pointRadius: 5,
                pointHoverRadius: 7
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: false, min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font: { weight: '600' } } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { weight: '600' } } }
            },
            plugins: { 
                legend: { display: false },
                tooltip: { backgroundColor: '#1a1f26', titleColor: '#00f2fe', bodyColor: '#fff', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1 }
            }
        }
    });

    // 2. Gráfico por Tipo (Bar)
    const types = Object.keys(data.distribucion_tipo);
    const typeCounts = types.map(t => data.distribucion_tipo[t].Item);
    
    chartType = new Chart(canvasType, {
        type: 'bar',
        data: {
            labels: types,
            datasets: [{
                label: 'Cant. de Ítems',
                data: typeCounts,
                backgroundColor: [
                    'rgba(79, 172, 254, 0.6)', 
                    'rgba(245, 158, 11, 0.6)', 
                    'rgba(16, 185, 129, 0.6)'
                ],
                borderColor: ['#4facfe', '#f59e0b', '#10b981'],
                borderWidth: 2,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font: { weight: '600' } } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { weight: '600' } } }
            },
            plugins: { 
                legend: { display: false },
                tooltip: { backgroundColor: '#1a1f26', titleColor: '#00f2fe', bodyColor: '#fff', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1 }
            }
        }
    });
}

// =========================================
// INFORMACIÓN DEL SERVIDOR [NUEVO]
// =========================================
async function initServerInfo() {
    try {
        const res = await fetch('/api/server/ip');
        const data = await res.json();
        const el = document.getElementById('access-url');
        if (el) el.textContent = data.url;
    } catch (err) {
        console.error("Error obteniendo IP:", err);
    }
}

function copyAccessUrl() {
    const el = document.getElementById('access-url');
    if (!el) return;
    const url = el.textContent;
    navigator.clipboard.writeText(url).then(() => {
        alert("¡Enlace copiado al portapapeles! 🚀\nPuedes pegarlo y enviarlo a tu equipo.");
    }).catch(err => {
        console.error('Error al copiar:', err);
        // Fallback para entornos sin soporte de portapapeles simple
        const tempInput = document.createElement('input');
        tempInput.value = url;
        document.body.appendChild(tempInput);
        tempInput.select();
        document.execCommand('copy');
        document.body.removeChild(tempInput);
        alert("¡Enlace copiado! (Fallback)");
    });
}
