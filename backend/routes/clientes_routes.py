@clientes_blueprint.route('/clientes', methods=['POST'])
def registrar_cliente():
    try:
        datos = request.json
        
        rut = datos.get('rut', '').strip()
        direccion = datos.get('direccion', '').strip()
        nombre_contacto_1 = datos.get('nombre_contacto_1', '').strip()
        nombre_contacto_2 = datos.get('nombre_contacto_2', '').strip()
        telefono = datos.get('telefono', '').strip()
        email = datos.get('email', '').strip()
        area = datos.get('area', '')

        # Validación de campos según mockup
        if not all([rut, direccion, nombre_contacto_1, telefono, email, area]):
            return jsonify({"error": "Por favor, complete todos los campos mandatorios de la tabla."}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Error interno de base de datos."}), 500

        with conexion.cursor() as cursor:
            cursor.execute("SELECT id FROM clientes WHERE rut = %s", (rut,))
            if cursor.fetchone():
                return jsonify({"error": "El RUT ingresado ya existe en la firma."}), 400

            # Unificamos los contactos en el campo de la base de datos o si modificaron su tabla
            nombre_completo = f"{nombre_contacto_1} / {nombre_contacto_2}".strip(" / ")

            query = """
                INSERT INTO clientes (nombre, rut, email, telefono, direccion, area, estado)
                VALUES (%s, %s, %s, %s, %s, %s, 'Activo')
            """
            cursor.execute(query, (nombre_completo, rut, email, telefono, direccion, area))
            conexion.commit()

        return jsonify({"message": "Cliente incorporado."}), 201

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": "Fallo en el servidor."}), 500