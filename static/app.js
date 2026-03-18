// =========================================
// INICIALIZACIÓN Y VARIABLES
// =========================================
document.addEventListener("DOMContentLoaded", () => {
    initSemanas();
    loadFilters();
    loadKPIs(); // Carga inicial
    setupDragAndDrop();
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
        document.getElementById('sub-adicional').textContent = `vs Normales (${data.items_adicionales} órdenes)`;
        
        const popEl = document.getElementById('val-pop');
        if (popEl) popEl.textContent = `${data.pop}%`;
        
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
                    <td colspan="6" style="font-weight: 800; color: var(--accent); padding: 12px 15px;" onclick="toggleArea('${currentAreaIndex}')">
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
                        <td colspan="6" style="padding-left: 30px; font-weight: 600; color: var(--text-primary); cursor: pointer;" onclick="toggleOrden('${id_orden}')">
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
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--success); font-weight: 800; padding: 20px;">🎉 ¡No hay Backorders! Todo lo solicitado fue entregado.</td></tr>';
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
                <td style="text-align: center;">
                    <button class="btn-primary" onclick="guardarCambiosOrden(${ord.ID_Orden})" style="padding: 6px 12px; font-size: 12px; font-weight: 800; background: var(--accent); color: #0b0f15; border: none; border-radius: 4px; cursor: pointer;">💾 Guardar</button>
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
