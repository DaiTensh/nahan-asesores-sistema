function cargarTopbar() {
  const usuario = JSON.parse(localStorage.getItem("usuario"));

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  const topbar = document.getElementById("topbar");

  if (!topbar) return;

  const iniciales = usuario.nombres
    .split(" ")
    .map(nombre => nombre[0])
    .join("")
    .substring(0, 2)
    .toUpperCase();

  topbar.innerHTML = `
    <div class="topbar-search">
      <input type="text" placeholder="Buscar clientes, tareas, documentos...">
    </div>

    <div class="topbar-user">
      <div class="user-avatar">${iniciales}</div>

      <div class="user-info">
        <span class="user-name">${usuario.nombres}</span>
        <span class="user-role">${usuario.nombre_rol}</span>
      </div>
    </div>
  `;
}