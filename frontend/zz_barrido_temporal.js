// TEMPORAL (auditoría UX/UI): se elimina antes de commitear.
window.PAGINAS = ["dashboard/dashboard.html","clientes/listar_clientes.html","clientes/registrar_clientes.html","clientes/filtrar_clientes.html","clientes/ficha_cliente.html?id=1","clientes/modificar_clientes.html?id=1","clientes/cambiar_estado.html?id=1","clientes/eliminar_cliente.html?id=1","tareas/tareas.html","tareas/detalle_tarea.html?id=1","tareas/editar_tarea.html?id=1","control_horas/control_horas.html","reportes/reportes.html","reportes/productividad.html","reportes/historial_consolidado.html","historial/historial.html","usuarios/usuarios.html","usuarios/modificar_usuario.html?id=2","usuarios/desactivar_usuario.html","usuarios/asignar_rol.html","usuarios/configuracion_sesion.html","respaldos/respaldos.html"];
window.medir = function (win, ancho) {
  const d = win.document, out = {};
  out.h1 = d.querySelectorAll('h1').length;
  out.scrollW = d.documentElement.scrollWidth; out.desborde = out.scrollW > ancho + 1;
  const off = [];
  for (const el of d.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cs = win.getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || cs.position === 'fixed') continue;
    if (r.right > ancho + 1) {
      let p = el.parentElement, recortado = false;
      while (p && p !== d.body) { const ps = win.getComputedStyle(p); if (/(auto|scroll|hidden)/.test(ps.overflowX) && p.getBoundingClientRect().right <= ancho + 1) { recortado = true; break; } p = p.parentElement; }
      if (!recortado) off.push(el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '') + '#' + (el.id||'') + ' r' + Math.round(r.right));
    }
  }
  out.nOff = off.length; out.off = off.slice(0, 3);
  const sinNombre = [];
  d.querySelectorAll('button, a[href], [role=button]').forEach(el => {
    const n = (el.textContent || '').trim() || el.getAttribute('aria-label') || el.getAttribute('title');
    if (!n && el.getBoundingClientRect().width > 0) sinNombre.push(el.tagName.toLowerCase() + '#' + (el.id||''));
  });
  d.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea').forEach(el => {
    if (!(el.getBoundingClientRect().width > 0)) return;
    const tiene = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || (el.id && d.querySelector('label[for="' + el.id + '"]')) || el.closest('label');
    if (!tiene) sinNombre.push(el.tagName.toLowerCase() + '#' + (el.id || el.name || '') + '(sin etiqueta)');
  });
  out.sinNombre = sinNombre.slice(0, 5); out.nSinNombre = sinNombre.length;
  out.anchoUtil = Math.round((d.querySelector('.main-content') || d.body).getBoundingClientRect().width);
  return out;
};
window.barrer = async function (ancho, lista) {
  const res = {};
  for (const url of (lista || window.PAGINAS)) {
    const f = document.createElement('iframe');
    f.style.cssText = `position:absolute;left:0;top:0;width:${ancho}px;height:900px;border:0;visibility:hidden`;
    document.body.appendChild(f);
    await new Promise(ok => { f.onload = ok; f.src = '/' + url; });
    await new Promise(ok => setTimeout(ok, 1100));
    try { res[url] = medir(f.contentWindow, ancho); } catch (e) { res[url] = {error: String(e)}; }
    f.remove();
  }
  return res;
};
window.resumir = (r) => { const o = {}; for (const [u, m] of Object.entries(r)) { if (m.error) { o[u] = m.error; continue; } if (m.desborde || m.nOff || m.nSinNombre || m.h1 !== 1) o[u] = `h1=${m.h1} desb=${m.desborde} scrollW=${m.scrollW} nOff=${m.nOff} [${m.off.join(' | ')}] sinNombre=${m.nSinNombre} util=${m.anchoUtil}`; } return o; };
