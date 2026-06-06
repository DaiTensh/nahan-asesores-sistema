function cerrarSesion() {

    localStorage.removeItem("usuario");

    window.location.href = "../auth/login.html";

}