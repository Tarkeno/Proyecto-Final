from flask import Flask, request, jsonify, render_template
from flask_cors import CORS 
import psycopg2
import pandas as pd
import io
import qrcode

app = Flask(__name__)
CORS(app)


# Conexión a la base de datos
def conectar_bd():
    return psycopg2.connect(
        host="localhost",
        database="db_control",
        user="postgres",
        password="12345"
    )


@app.route("/api/modificar-reporte")
def modificar_reporte():
    matricula = request.args.get("matricula")
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")

    if not matricula or not inicio or not fin:
        return jsonify({"error": "Faltan parámetros"}), 400

    conn = conectar_bd()   # tu configuración de conexión
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
               e.carrera, e.semestre, e.grupo, a.fecha, a.estado_asistencia
        FROM asistencias a
        JOIN estudiantes e ON a.matricula = e.matricula
        WHERE a.matricula = %s AND a.fecha >= %s AND a.fecha < %s::date + INTERVAL '1 day'
        ORDER BY a.fecha
    """, (matricula, inicio, fin))

    resultados = cursor.fetchall()
    registros = []

    for r in resultados:
        registros.append({
            "matricula": r[0],
            "nombre": r[1],
            "apellido_paterno": r[2],
            "apellido_materno": r[3],
            "carrera": r[4],
            "semestre": r[5],
            "grupo": r[6],
            "fecha": r[7].strftime("%Y-%m-%d"),
            "estado_asistencia": r[8]  # ← ahora sí es estado_asistencia
        })

    cursor.close()
    conn.close()
    return jsonify(registros)

@app.route('/buscar_estudiante', methods=['POST'])
def buscar_estudiante():
    data = request.get_json()
    matricula = data.get("matricula")

    if not matricula:
        return jsonify({"error": "Matrícula no proporcionada"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT matricula, nombre, apellido_paterno, apellido_materno,
               carrera, semestre, grupo
        FROM estudiantes
        WHERE matricula = %s
    """, (matricula,))

    estudiante = cur.fetchone()
    cur.close()
    conn.close()

    if estudiante:
        return jsonify({
            "matricula": estudiante[0],
            "nombre": estudiante[1],
            "apellido_paterno": estudiante[2],
            "apellido_materno": estudiante[3],
            "carrera": estudiante[4],
            "semestre": estudiante[5],
            "grupo": estudiante[6]
        })
    else:
        return jsonify({"error": "Estudiante no encontrado"}), 404
    
@app.route('/buscar_personal', methods=['POST'])
def buscar_personal():
    data = request.get_json()
    clave = data.get("clave")

    if not clave:
        return jsonify({"error": "Clave no proporcionada"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT clave, nombre, apellido_paterno, apellido_materno,
               puesto
        FROM personal
        WHERE clave = %s
    """, (clave,))

    persona = cur.fetchone()
    cur.close()
    conn.close()

    if persona:
        return jsonify({
            "clave": persona[0],
            "nombre": persona[1],
            "apellido_paterno": persona[2],
            "apellido_materno": persona[3],
            "puesto": persona[4]
        })
    else:
        return jsonify({"error": "Personal no encontrado"}), 404


# 🗑️ Eliminar un registro
@app.route('/api/eliminar-registro', methods=['POST'])
def eliminar_registro():
    data = request.get_json()
    matricula = data.get("matricula")
    fecha = data.get("fecha")

    if not matricula or not fecha:
        return jsonify({"success": False, "message": "Faltan datos"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM asistencias
            WHERE matricula = %s AND fecha = %s
        """, (matricula, fecha))

        conn.commit()

        if cur.rowcount > 0:
            return jsonify({"success": True, "message": "Registro eliminado correctamente"}), 200
        else:
            return jsonify({"success": False, "message": "No se encontró registro con esa matrícula y fecha"}), 404

    except Exception as e:
        conn.rollback()
        print("Error al eliminar registro:", e)
        return jsonify({"success": False, "message": "Error al eliminar registro"}), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/reporte")
def generar_reporte_general():
    tipo = request.args.get("tipo")
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")
    matricula = request.args.get("matricula")  # opcional

    if not tipo or not inicio or not fin:
        return jsonify({"error": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cursor = conn.cursor()

    try:
        if tipo == "general":
            query = """
                SELECT a.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                       e.carrera, e.semestre, e.grupo,
                       COUNT(CASE WHEN a.estado_asistencia = 'Asistencia' THEN 1 END) AS asistencias,
                       COUNT(CASE WHEN a.estado_asistencia = 'Inasistencia' THEN 1 END) AS inasistencias,
                       COUNT(CASE WHEN a.estado_asistencia = 'Justificación' THEN 1 END) AS justificaciones
                FROM asistencias a
                JOIN estudiantes e ON a.matricula = e.matricula
                WHERE a.fecha >= %s AND a.fecha < %s::date + INTERVAL '1 day'
            """
            params = [inicio, fin]
            if matricula:
                query += " AND a.matricula = %s"
                params.append(matricula)
            query += " GROUP BY a.matricula, e.nombre, e.apellido_paterno, e.apellido_materno, e.carrera, e.semestre, e.grupo ORDER BY e.nombre"

        elif tipo in ["asistencias", "inasistencias", "justificaciones"]:
            estado = {
                "asistencias": "Asistencia",
                "inasistencias": "Inasistencia",
                "justificaciones": "Justificación"
            }[tipo]

            query = """
                SELECT a.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                       e.carrera, e.semestre, e.grupo, a.fecha
                FROM asistencias a
                JOIN estudiantes e ON a.matricula = e.matricula
                WHERE a.estado_asistencia = %s
                  AND a.fecha >= %s AND a.fecha < %s::date + INTERVAL '1 day'
            """
            params = [estado, inicio, fin]
            if matricula:
                query += " AND a.matricula = %s"
                params.append(matricula)
            query += " ORDER BY a.fecha"
        else:
            return jsonify({"error": "Tipo de reporte no soportado"}), 400

        cursor.execute(query, params)
        resultados = cursor.fetchall()

        if not resultados:
            return jsonify({"message": "No se encontraron registros"}), 404

        # Construcción de registros
        if tipo == "general":
            registros = [{
                "matricula": r[0],
                "nombre": r[1],
                "apellido_paterno": r[2],
                "apellido_materno": r[3],
                "carrera": r[4],
                "semestre": r[5],
                "grupo": r[6],
                "asistencias": r[7],
                "inasistencias": r[8],
                "justificaciones": r[9]
            } for r in resultados]
        else:
            registros = [{
                "matricula": r[0],
                "nombre": r[1],
                "apellido_paterno": r[2],
                "apellido_materno": r[3],
                "carrera": r[4],
                "semestre": r[5],
                "grupo": r[6],
                "fecha": r[7].strftime("%Y-%m-%d")
            } for r in resultados]

        return jsonify(registros)

    except Exception as e:
        print("Error al generar reporte:", e)
        return jsonify({"error": "Error al generar reporte"}), 500
    finally:
        cursor.close()
        conn.close()
@app.route("/agregar")
def vista_agregar_estudiante():
    return render_template("agregar.html")

@app.route('/api/agregar_estudiante', methods=['POST'])
def agregar_estudiante():
    data = request.get_json()

    matricula = data.get("matricula")
    nombre = data.get("nombre")
    apellido_paterno = data.get("apellido_paterno")
    apellido_materno = data.get("apellido_materno")
    carrera = data.get("carrera")   # texto
    semestre = data.get("semestre") # número
    grupo = data.get("grupo")       # texto

    if not all([matricula, nombre, apellido_paterno, apellido_materno, carrera, semestre, grupo]):
        return jsonify({"success": False, "message": "Faltan datos obligatorios"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO estudiantes (matricula, nombre, apellido_paterno, apellido_materno, carrera, semestre, grupo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (matricula, nombre, apellido_paterno, apellido_materno, carrera, semestre, grupo))

        conn.commit()
        return jsonify({"success": True, "message": "Estudiante agregado correctamente"}), 201

    except Exception as e:
        conn.rollback()
        print("Error al insertar estudiante:", e)
        return jsonify({"success": False, "message": "Error al insertar en la base de datos"}), 500

    finally:
        cur.close()
        conn.close()

@app.route('/api/eliminar_estudiante', methods=['POST'])
def eliminar_estudiante():
    data = request.get_json()
    matricula = data.get("matricula")

    if not matricula:
        return jsonify({"success": False, "message": "Falta la matrícula"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM estudiantes WHERE matricula = %s", (matricula,))
        conn.commit()

        filas_afectadas = cur.rowcount

        if filas_afectadas > 0:
            return jsonify({"success": True, "message": "Estudiante eliminado correctamente"}), 200
        else:
            return jsonify({"success": False, "message": "No se encontró estudiante con esa matrícula"}), 404

    except Exception as e:
        conn.rollback()
        print("Error al eliminar estudiante:", e)
        return jsonify({"success": False, "message": "Error al eliminar en la base de datos"}), 500

    finally:
        cur.close()
        conn.close()

@app.route('/api/actualizar_estudiante', methods=['PUT'])
def actualizar_estudiante():
    data = request.get_json() or {}
    matricula = data.get("matricula")

    if not matricula:
        return jsonify({"success": False, "message": "Falta la matrícula"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE estudiantes
            SET nombre=%s, apellido_paterno=%s, apellido_materno=%s,
                carrera=%s, semestre=%s, grupo=%s
            WHERE matricula=%s
        """, (
            data.get("nombre"),
            data.get("apellido_paterno"),
            data.get("apellido_materno"),
            data.get("carrera"),   # texto
            data.get("semestre"),  # número
            data.get("grupo"),     # texto
            matricula
        ))

        conn.commit()
        filas_afectadas = cur.rowcount

        if filas_afectadas > 0:
            return jsonify({"success": True, "message": "Estudiante actualizado correctamente"}), 200
        else:
            return jsonify({"success": False, "message": "No se encontró estudiante con esa matrícula"}), 404

    except Exception as e:
        conn.rollback()
        print("Error al actualizar estudiante:", e)
        return jsonify({"success": False, "message": "Error al actualizar"}), 500

    finally:
        cur.close()
        conn.close()


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    usuario = data.get("usuario")
    contraseña = data.get("contraseña")

    if not usuario or not contraseña:
        return jsonify({"success": False, "message": "Faltan credenciales"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, nombre, apellido_paterno, apellido_materno, rol, es_maestro
        FROM usuarios
        WHERE usuario = %s AND contraseña = %s
    """, (usuario, contraseña))

    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado:
        return jsonify({
            "success": True,
            "usuario": usuario,
            "rol": resultado[4],
            "es_maestro": resultado[5]
        })
    else:
        return jsonify({"success": False, "message": "Credenciales incorrectas"})

@app.route("/api/validar-master", methods=["POST"])
def validar_master():
    data = request.get_json()
    usuario = data.get("usuario")
    contraseña = data.get("contraseña")

    if not usuario or not contraseña:
        return jsonify({"success": False, "message": "Faltan credenciales"}), 400

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT rol, es_maestro
        FROM usuarios
        WHERE usuario = %s AND contraseña = %s
    """, (usuario, contraseña))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Credenciales incorrectas"})


@app.route("/api/reset-asistencias-alumnos", methods=["DELETE"])
def reset_asistencias_alumnos():
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("DELETE FROM asistencias")  # tabla de alumnos
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "✅ Asistencias de alumnos borradas"})

@app.route("/api/reset-asistencias-personal", methods=["DELETE"])
def reset_asistencias_personal():
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("DELETE FROM asistencias_personal")  # tabla de personal
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "✅ Asistencias de personal borradas"})



@app.route("/api/listar_estudiantes", methods=["GET"])
def listar_estudiantes():
    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT matricula, nombre, apellido_paterno, apellido_materno,
                   carrera, semestre, grupo
            FROM estudiantes
        """)

        estudiantes = cur.fetchall()

        if not estudiantes:
            return jsonify({"success": False, "message": "No hay estudiantes registrados"}), 404

        resultado = [{
            "matricula": est[0],
            "nombre": est[1],
            "apellido_paterno": est[2],
            "apellido_materno": est[3],
            "carrera": est[4].title() if est[4] else None,
            "semestre": est[5],
            "grupo": est[6]
        } for est in estudiantes]

        return jsonify({"success": True, "estudiantes": resultado}), 200

    except Exception as e:
        print("Error al listar estudiantes:", e)
        return jsonify({"success": False, "message": "Error al obtener estudiantes"}), 500

    finally:
        cur.close()
        conn.close()

@app.route('/api/registrar_usuario', methods=['POST'])
def registrar_usuario():
    data = request.get_json()

    nombre = data.get("nombre")
    apellido_paterno = data.get("apellido_paterno")
    apellido_materno = data.get("apellido_materno")
    usuario = data.get("usuario")
    contraseña = data.get("contraseña")
    rol = data.get("rol")
    es_maestro = data.get("es_maestro", False)

    if not all([nombre, apellido_paterno, apellido_materno, usuario, contraseña, rol]):
        return jsonify({"success": False, "message": "Faltan datos obligatorios"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO usuarios (nombre, apellido_paterno, apellido_materno, usuario, contraseña, rol, es_maestro)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (nombre, apellido_paterno, apellido_materno, usuario, contraseña, rol, es_maestro))

        conn.commit()
        return jsonify({"success": True, "message": "Usuario registrado correctamente"}), 201

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"success": False, "message": "El usuario ya existe"}), 409

    except Exception as e:
        conn.rollback()
        print("Error al registrar usuario:", e)
        return jsonify({"success": False, "message": "Error al insertar en la base de datos"}), 500

    finally:
        cur.close()
        conn.close()

# Listar personal
@app.route("/api/listar_personal", methods=["GET"])
def listar_personal():
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute("SELECT clave, nombre, apellido_paterno, apellido_materno, puesto FROM personal")
        rows = cur.fetchall()
        personal = []
        for r in rows:
            personal.append({
                "clave": r[0],
                "nombre": r[1],
                "apellido_paterno": r[2],
                "apellido_materno": r[3],
                "puesto": r[4]
            })
        return jsonify({"success": True, "personal": personal}), 200
    except Exception as e:
        print("Error al listar personal:", e)
        return jsonify({"success": False, "message": "Error al listar personal"}), 500
    finally:
        cur.close()
        conn.close()


# Agregar personal
@app.route("/api/agregar_personal", methods=["POST"])
def agregar_personal():
    data = request.get_json()
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO personal (clave, nombre, apellido_paterno, apellido_materno, puesto)
            VALUES (%s, %s, %s, %s, %s)
        """, (data["clave"], data["nombre"], data["apellido_paterno"], data["apellido_materno"], data["puesto"]))
        conn.commit()
        return jsonify({"success": True, "message": "Personal agregado correctamente"}), 200
    except Exception as e:
        conn.rollback()
        print("Error al agregar personal:", e)
        return jsonify({"success": False, "message": "Error al agregar personal"}), 500
    finally:
        cur.close()
        conn.close()
@app.route("/agregar-personal")
def vista_agregar_personal():
    return render_template("agregar_personal.html")


# Actualizar personal
@app.route("/api/actualizar_personal/<clave>", methods=["PUT"])
def actualizar_personal(clave):
    data = request.get_json()
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE personal
            SET nombre=%s, apellido_paterno=%s, apellido_materno=%s, puesto=%s
            WHERE clave=%s
        """, (data["nombre"], data["apellido_paterno"], data["apellido_materno"], data["puesto"], clave))
        conn.commit()
        return jsonify({"success": True, "message": "Personal actualizado correctamente"}), 200
    except Exception as e:
        conn.rollback()
        print("Error al actualizar personal:", e)
        return jsonify({"success": False, "message": "Error al actualizar personal"}), 500
    finally:
        cur.close()
        conn.close()


# Eliminar personal
@app.route("/api/eliminar_personal/<clave>", methods=["DELETE"])
def eliminar_personal(clave):
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM personal WHERE clave=%s", (clave,))
        filas_afectadas = cur.rowcount
        conn.commit()
        if filas_afectadas > 0:
            return jsonify({"success": True, "message": "Personal eliminado correctamente"}), 200
        else:
            return jsonify({"success": False, "message": "No se encontró personal con esa clave"}), 404
    except Exception as e:
        conn.rollback()
        print("Error al eliminar personal:", e)
        return jsonify({"success": False, "message": "Error al eliminar personal"}), 500
    finally:
        cur.close()
        conn.close()

@app.route("/docentes")
def vista_docentes():
    return render_template("docentes.html")

@app.route("/estudiantes")
def vista_estudiantes():
    return render_template("estudiantes.html")

@app.route("/reporte-docentes-asistencias")
def vista_reporte_docentes_asistencias():
    return render_template("Generar_Reporte_Docentes_Asistencias.html")


@app.route("/reporte-docentes-general")
def vista_reporte_docentes_general():
    return render_template("Generar_reporte_docentes_general.html")

@app.route("/reporte-docentes-inasistencias")
def vista_reporte_docentes_inasistencias():
    return render_template("Generar_Reporte_Docentes_Inasistencias.html")

@app.route("/reporte-docentes-justificaciones")
def vista_reporte_docentes_justificaciones():
    return render_template("Generar_Reporte_Docentes_Justificaciones.html")

@app.route("/reporte-estudiantes-asistencias")
def vista_reporte_estudiantes_asistencias():
    return render_template("Generar_Reporte_Estudiantes_Asistencias.html")

@app.route("/reporte-estudiantes-general")
def vista_reporte_estudiantes_general():
    return render_template("Generar_Reporte_Estudiantes_General.html")

@app.route("/reporte-estudiantes-inasistencias")
def vista_reporte_estudiantes_inasistencias():
    return render_template("Generar_Reporte_Estudiantes_Inasistencias.html")

@app.route("/reporte-estudiantes-justificaciones")
def vista_reporte_estudiantes_justificaciones():
    return render_template("Generar_Reporte_Estudiantes_Justificaciones.html")

@app.route("/historial")
def vista_historial():
    return render_template("historial.html")

@app.route("/informacion-docente")
def vista_informacion_docente():
    return render_template("informacion_docente.html")

@app.route("/informacion-estudiante")
def vista_informacion_estudiante():
    return render_template("informacion_estudiante.html")

@app.route("/")
def vista_login():
    return render_template("login.html")

@app.route("/login")
def login_vista():
    return render_template("login.html")

@app.route("/modificar-reporte-docentes")
def vista_modificar_reporte_docentes():
    return render_template("Modificar_Reporte_Docentes.html")

@app.route("/modificar-reporte-estudiantes")
def vista_modificar_reporte_estudiantes():
    return render_template("Modificar_Reporte_Estudiantes.html")

@app.route("/panel-inicio")
def vista_panel_inicio():
    return render_template("panel_inicio.html")

@app.route("/registro")
def vista_registro():
    return render_template("registro.html")

@app.route("/reporte-docentes")
def vista_reporte_docentes():
    return render_template("reporte_docentes.html")

@app.route("/reporte-estudiantes")
def vista_reporte_estudiantes():
    return render_template("reporte_estudiantes.html")

@app.route("/reportes-grupales-estudiantes-asistencias")
def vista_rg_estudiantes_asistencias():
    return render_template("Reportes_Grupales_Estudiantes_Asistencias.html")

@app.route("/reportes-grupales-estudiantes-general")
def vista_rg_estudiantes_general():
    return render_template("Reportes_Grupales_Estudiantes_General.html")

@app.route("/reportes-grupales-estudiantes-inasistencias")
def vista_rg_estudiantes_inasistencias():
    return render_template("Reportes_Grupales_Estudiantes_Inasistencias.html")

@app.route("/reportes-grupales-estudiantes-justificaciones")
def vista_rg_estudiantes_justificaciones():
    return render_template("Reportes_Grupales_Estudiantes_Justificaciones.html")

@app.route("/reportes-grupales-docentes-asistencias")
def vista_rg_docentes_asistencias():
    return render_template("Reportes_Grupales_Docentes_Asistencias.html")

@app.route("/reportes-grupales-docentes-general")
def vista_rg_docentes_general():
    return render_template("Reportes_Grupales_Docentes_General.html")

@app.route("/reportes-grupales-docentes-inasistencias")
def vista_rg_docentes_inasistencias():
    return render_template("Reportes_Grupales_Docentes_Inasistencias.html")

@app.route("/reportes-grupales-docentes-justificaciones")
def vista_rg_docentes_justificaciones():
    return render_template("Reportes_Grupales_Docentes_Justificaciones.html")

@app.route("/reportes-grupales-administrativo-asistencias")
def vista_rg_admin_asistencias():
    return render_template("Reportes_Grupales_Administrativo_Asistencias.html")

@app.route("/reportes-grupales-administrativo-general")
def vista_rg_admin_general():
    return render_template("Reportes_Grupales_Administrativo_General.html")

@app.route("/reportes-grupales-administrativo-inasistencias")
def vista_rg_admin_inasistencias():
    return render_template("Reportes_Grupales_Administrativo_Inasistencias.html")

@app.route("/reportes-grupales-administrativo-justificaciones")
def vista_rg_admin_justificaciones():
    return render_template("Reportes_Grupales_Administrativo_Justificaciones.html")

@app.route("/reportes")
def vista_reportes():
    return render_template("reportes.html")



@app.route("/api/modificar-reporte-personal", methods=["GET"])
def modificar_reporte_personal():
    clave = request.args.get("clave")
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")

    if not clave or not inicio or not fin:
        return jsonify({"error": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT p.clave, p.nombre, p.apellido_paterno, p.apellido_materno,
                   p.puesto, ap.fecha, ap.estado_asistencia
            FROM asistencias_personal ap
            JOIN personal p ON ap.personal_id = p.id
            WHERE p.clave = %s
              AND ap.fecha >= %s
              AND ap.fecha < %s::date + INTERVAL '1 day'
            ORDER BY ap.fecha
        """, (clave, inicio, fin))

        resultados = cur.fetchall()

        registros = []
        for r in resultados:
            registros.append({
                "clave": r[0],
                "nombre": r[1],
                "apellido_paterno": r[2],
                "apellido_materno": r[3],
                "puesto": r[4],
                "fecha": r[5].strftime("%Y-%m-%d"),
                "estado_asistencia": r[6]
            })

        return jsonify(registros), 200

    except Exception as e:
        print("Error al modificar reporte personal:", e)
        return jsonify({"error": "Error al obtener registros"}), 500

    finally:
        cur.close()
        conn.close()

# Reportes de asistencia del personal
@app.route("/api/reporte_personal")
def generar_reporte_personal():
    tipo = request.args.get("tipo")
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")
    clave = request.args.get("clave")  # opcional

    if not tipo or not inicio or not fin:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cursor = conn.cursor()

    try:
        if tipo == "general":
            query = """
                SELECT p.id, p.clave, p.nombre, p.apellido_paterno, p.apellido_materno, p.puesto,
                       COUNT(CASE WHEN a.estado_asistencia = 'Asistencia' THEN 1 END) AS asistencias,
                       COUNT(CASE WHEN a.estado_asistencia = 'Inasistencia' THEN 1 END) AS inasistencias,
                       COUNT(CASE WHEN a.estado_asistencia = 'Justificación' THEN 1 END) AS justificaciones
                FROM asistencias_personal a
                JOIN personal p ON a.personal_id = p.id
                WHERE a.fecha >= %s AND a.fecha <= %s
            """
            params = [inicio, fin]

            if clave:
                query += " AND p.clave = %s"
                params.append(clave)

            query += """
                GROUP BY p.id, p.clave, p.nombre, p.apellido_paterno, p.apellido_materno, p.puesto
                ORDER BY p.nombre
            """

        elif tipo in ["asistencias", "inasistencias", "justificaciones"]:
            estado = {
                "asistencias": "Asistencia",
                "inasistencias": "Inasistencia",
                "justificaciones": "Justificación"
            }[tipo]

            query = """
                SELECT p.clave, p.nombre, p.apellido_paterno, p.apellido_materno, p.puesto,
                       a.fecha, a.estado_asistencia
                FROM asistencias_personal a
                JOIN personal p ON a.personal_id = p.id
                WHERE a.estado_asistencia = %s
                  AND a.fecha >= %s AND a.fecha <= %s
            """
            params = [estado, inicio, fin]

            if clave:
                query += " AND p.clave = %s"
                params.append(clave)

            query += " ORDER BY a.fecha"

        else:
            return jsonify({"success": False, "message": "Tipo de reporte no soportado"}), 400

        cursor.execute(query, params)
        resultados = cursor.fetchall()

        if not resultados:
            return jsonify({"success": False, "message": "No se encontraron registros"}), 404

        if tipo == "general":
            registros = [{
                "id": r[0],
                "clave": r[1],
                "nombre": r[2],
                "apellido_paterno": r[3],
                "apellido_materno": r[4],
                "puesto": r[5],
                "asistencias": r[6],
                "inasistencias": r[7],
                "justificaciones": r[8]
            } for r in resultados]
        else:
            registros = [{
                "clave": r[0],
                "nombre": r[1],
                "apellido_paterno": r[2],
                "apellido_materno": r[3],
                "puesto": r[4],
                "fecha": r[5].strftime("%Y-%m-%d"),
                "estado_asistencia": r[6]
            } for r in resultados]

        return jsonify({"success": True, "registros": registros}), 200

    except Exception as e:
        print("Error al generar reporte de personal:", e)
        return jsonify({"success": False, "message": "Error al generar reporte"}), 500

    finally:
        cursor.close()
        conn.close()


# Guardar cambios en asistencias del personal
@app.route("/api/guardar-cambios-personal", methods=["POST"])
def guardar_cambios_personal():
    data = request.get_json()
    cambios = data.get("cambios", [])

    if not cambios:
        return jsonify({"success": False, "message": "No se recibieron cambios"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        for cambio in cambios:
            clave = cambio.get("clave")
            fecha = cambio.get("fecha")
            estado = cambio.get("estado_asistencia")

            if not clave or not fecha or not estado:
                return jsonify({"success": False, "message": "Datos incompletos en un cambio"}), 400

            cur.execute("""
                UPDATE asistencias_personal
                SET estado_asistencia = %s
                WHERE personal_id = (SELECT id FROM personal WHERE clave = %s)
                  AND fecha = %s
            """, (estado, clave, fecha))

        conn.commit()
        return jsonify({"success": True, "message": "Cambios guardados correctamente"}), 200

    except Exception as e:
        conn.rollback()
        print("Error al guardar cambios:", e)
        return jsonify({"success": False, "message": "Error al guardar cambios"}), 500

    finally:
        cur.close()
        conn.close()


# Eliminar registro de asistencia del personal
@app.route("/api/eliminar-registro-personal", methods=["POST"])
def eliminar_registro_personal():
    data = request.get_json()
    clave = data.get("clave")
    fecha = data.get("fecha")

    if not clave or not fecha:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM asistencias_personal
            WHERE personal_id = (SELECT id FROM personal WHERE clave = %s)
              AND fecha = %s
        """, (clave, fecha))

        filas_afectadas = cur.rowcount
        conn.commit()

        if filas_afectadas > 0:
            return jsonify({"success": True, "message": "Registro eliminado correctamente"}), 200
        else:
            return jsonify({"success": False, "message": "No se encontró registro con esa clave y fecha"}), 404

    except Exception as e:
        conn.rollback()
        print("Error al eliminar registro:", e)
        return jsonify({"success": False, "message": "Error al eliminar registro"}), 500

    finally:
        cur.close()
        conn.close()
# Eliminar registro de asistencia de estudiantes
@app.route("/api/eliminar-registro-estudiante", methods=["POST"])
def eliminar_registro_estudiante():
    data = request.get_json()
    matricula = data.get("matricula")
    fecha = data.get("fecha")

    if not matricula or not fecha:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM asistencias
            WHERE matricula = %s AND fecha = %s
        """, (matricula, fecha))

        filas_afectadas = cur.rowcount
        conn.commit()

        if filas_afectadas > 0:
            return jsonify({"success": True, "message": "Registro eliminado correctamente"}), 200
        else:
            return jsonify({"success": False, "message": "No se encontró registro con esa matrícula y fecha"}), 404

    except Exception as e:
        conn.rollback()
        print("Error al eliminar registro de estudiante:", e)
        return jsonify({"success": False, "message": "Error al eliminar registro"}), 500

    finally:
        cur.close()
        conn.close()


# Listar asistencias con filtros avanzados
@app.route("/api/listar-asistencias", methods=["POST"])
def listar_asistencias():
    data = request.get_json()
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")
    comunidad = data.get("comunidad")
    tipo_reporte = data.get("tipo_reporte")

    carrera = data.get("carrera")
    semestre = data.get("semestre")
    grupo = data.get("grupo")

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        if comunidad == "estudiantes":
            query = """
                SELECT e.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                       e.carrera, e.semestre, e.grupo,
                       to_char(a.fecha AT TIME ZONE 'America/Mexico_City', 'DD/MM/YYYY HH12:MI AM') AS fecha,
                       a.estado_asistencia
                FROM asistencias a
                JOIN estudiantes e ON a.matricula = e.matricula
                WHERE a.fecha BETWEEN %s AND %s
            """
            params = [fecha_inicio, fecha_fin]

            if carrera:
                query += " AND e.carrera = %s"
                params.append(carrera)
            if semestre:
                query += " AND e.semestre = %s"
                params.append(semestre)
            if grupo:
                query += " AND e.grupo = %s"
                params.append(grupo)

        elif comunidad in ["personal", "docentes", "administrativo"]:
            query = """
                SELECT p.clave, p.nombre, p.apellido_paterno, p.apellido_materno,
                       p.puesto,
                       to_char(a.fecha AT TIME ZONE 'America/Mexico_City', 'DD/MM/YYYY HH12:MI AM') AS fecha,
                       a.estado_asistencia
                FROM asistencias_personal a
                JOIN personal p ON a.personal_id = p.id
                WHERE a.fecha BETWEEN %s AND %s
            """
            params = [fecha_inicio, fecha_fin]

            if comunidad == "docentes":
                query += " AND p.puesto = %s"
                params.append("Docente")

            elif comunidad == "administrativo":
                query += " AND p.puesto IN (%s, %s, %s)"
                params.extend(["Administrativo", "Coordinador", "Dirección"])

        else:
            return jsonify({"success": False, "message": "Comunidad no válida"}), 400

        if tipo_reporte == "asistencias":
            query += " AND a.estado_asistencia = 'Asistencia'"
        elif tipo_reporte == "inasistencias":
            query += " AND a.estado_asistencia = 'Inasistencia'"
        elif tipo_reporte == "justificaciones":
            query += " AND a.estado_asistencia = 'Justificación'"

        query += " ORDER BY a.fecha DESC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        resultados = []
        for r in rows:
            registro = {
                "fecha": r[-2],
                "estado_asistencia": r[-1]
            }

            if comunidad == "estudiantes":
                registro.update({
                    "matricula": r[0],
                    "nombre": r[1],
                    "apellido_paterno": r[2],
                    "apellido_materno": r[3],
                    "carrera": r[4],
                    "semestre": r[5],
                    "grupo": r[6]
                })
            else:
                registro.update({
                    "clave": r[0],
                    "nombre": r[1],
                    "apellido_paterno": r[2],
                    "apellido_materno": r[3],
                    "puesto": r[4]
                })

            resultados.append(registro)

        return jsonify({"success": True, "resultados": resultados}), 200

    except Exception as e:
        print("Error al listar asistencias:", e)
        return jsonify({"success": False, "message": "Error al generar reporte"}), 500

    finally:
        cur.close()
        conn.close()
@app.route("/api/asistencias-hoy", methods=["GET"])
def asistencias_hoy():
    conn = psycopg2.connect("dbname=db_control user=postgres password=12345 host=localhost port=5432")
    cur = conn.cursor()

    try:
        # Alumnos
        cur.execute("""
            SELECT e.matricula,
                   e.nombre,
                   to_char(a.fecha_dia, 'DD/MM/YYYY') AS fecha,
                   CASE
                       WHEN a.hora_entrada IS NOT NULL
                       THEN to_char(a.hora_entrada AT TIME ZONE 'America/Mexico_City', 'HH12:MI AM')
                       ELSE ''
                   END AS hora_entrada,
                   CASE
                       WHEN a.hora_salida IS NOT NULL
                       THEN to_char(a.hora_salida AT TIME ZONE 'America/Mexico_City', 'HH12:MI AM')
                       ELSE ''
                   END AS hora_salida,
                   a.estado_asistencia
            FROM asistencias a
            JOIN estudiantes e ON a.matricula = e.matricula
            WHERE a.fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            ORDER BY a.hora_entrada DESC NULLS LAST, a.fecha DESC
        """)
        alumnos = [
            {
                "matricula": row[0],
                "nombre": row[1],
                "fecha": row[2],
                "hora_entrada": row[3],
                "hora_salida": row[4],
                "estado": row[5]
            }
            for row in cur.fetchall()
        ]

        # Personal
        cur.execute("""
            SELECT p.clave,
                   p.nombre,
                   to_char(ap.fecha_dia, 'DD/MM/YYYY') AS fecha,
                   CASE
                       WHEN ap.hora_entrada IS NOT NULL
                       THEN to_char(ap.hora_entrada AT TIME ZONE 'America/Mexico_City', 'HH12:MI AM')
                       ELSE ''
                   END AS hora_entrada,
                   CASE
                       WHEN ap.hora_salida IS NOT NULL
                       THEN to_char(ap.hora_salida AT TIME ZONE 'America/Mexico_City', 'HH12:MI AM')
                       ELSE ''
                   END AS hora_salida,
                   ap.estado_asistencia
            FROM asistencias_personal ap
            JOIN personal p ON ap.personal_id = p.id
            WHERE ap.fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            ORDER BY ap.hora_entrada DESC NULLS LAST, ap.fecha DESC
        """)
        personal = [
            {
                "clave": row[0],
                "nombre": row[1],
                "fecha": row[2],
                "hora_entrada": row[3],
                "hora_salida": row[4],
                "estado": row[5]
            }
            for row in cur.fetchall()
        ]

        return jsonify({"alumnos": alumnos, "personal": personal})

    except Exception as e:
        print("Error en asistencias_hoy:", e)
        return jsonify({"alumnos": [], "personal": [], "error": "No se pudo cargar el historial"}), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/registrar-asistencia", methods=["GET", "POST"])
def registrar_asistencia():
    if request.method == "POST":
        data = request.get_json() or {}
        codigo = data.get("codigo_qr")
    else:
        codigo = request.args.get("codigo_qr")

    if not codigo:
        return jsonify({
            "success": False,
            "message": "No se recibió código QR"
        }), 400

    codigo = str(codigo).strip()

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        # =========================
        # BUSCAR ESTUDIANTE
        # =========================
        cur.execute("""
            SELECT matricula, nombre
            FROM estudiantes
            WHERE matricula::text = %s
        """, (codigo,))
        alumno = cur.fetchone()

        if alumno:
            matricula, nombre = alumno

            # Buscar registro del día
            cur.execute("""
                SELECT id, estado_asistencia, hora_entrada, hora_salida
                FROM asistencias
                WHERE matricula = %s
                  AND fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            """, (matricula,))
            registro = cur.fetchone()

            # Si no existe registro hoy: crear ENTRADA
            if not registro:
                cur.execute("""
                    INSERT INTO asistencias (
                        matricula, fecha, fecha_dia, hora_entrada, hora_salida, estado_asistencia
                    )
                    VALUES (
                        %s,
                        CURRENT_TIMESTAMP,
                        (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date,
                        CURRENT_TIMESTAMP,
                        NULL,
                        'Asistencia'
                    )
                """, (matricula,))
                conn.commit()
                cur.close()
                conn.close()

                return jsonify({
                    "success": True,
                    "tipo_registro": "entrada",
                    "message": f"Entrada registrada: {nombre}",
                    "nombre": nombre,
                    "matricula": matricula,
                    "estado": "Asistencia"
                })

            asistencia_id, estado_actual, hora_entrada, hora_salida = registro

            # Si existe pero no tiene entrada aún (por ejemplo, tenía inasistencia automática)
            if hora_entrada is None:
                cur.execute("""
                    UPDATE asistencias
                    SET hora_entrada = CURRENT_TIMESTAMP,
                        estado_asistencia = 'Asistencia',
                        fecha = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (asistencia_id,))
                conn.commit()
                cur.close()
                conn.close()

                return jsonify({
                    "success": True,
                    "tipo_registro": "entrada",
                    "message": f"Entrada registrada: {nombre}",
                    "nombre": nombre,
                    "matricula": matricula,
                    "estado": "Asistencia"
                })

            # Si ya tiene entrada pero no salida: registrar SALIDA
            if hora_salida is None:
                cur.execute("""
                    UPDATE asistencias
                    SET hora_salida = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (asistencia_id,))
                conn.commit()
                cur.close()
                conn.close()

                return jsonify({
                    "success": True,
                    "tipo_registro": "salida",
                    "message": f"Salida registrada: {nombre}",
                    "nombre": nombre,
                    "matricula": matricula,
                    "estado": estado_actual
                })

            # Si ya tiene entrada y salida
            cur.close()
            conn.close()
            return jsonify({
                "success": False,
                "message": f"Entrada y salida ya registradas hoy para {nombre}",
                "nombre": nombre,
                "matricula": matricula,
                "estado": estado_actual
            })

        # =========================
        # BUSCAR PERSONAL
        # =========================
        cur.execute("""
            SELECT id, clave, nombre
            FROM personal
            WHERE clave::text = %s
        """, (codigo,))
        persona = cur.fetchone()

        if persona:
            personal_id, clave, nombre = persona

            cur.execute("""
                SELECT id, estado_asistencia, hora_entrada, hora_salida
                FROM asistencias_personal
                WHERE personal_id = %s
                  AND fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            """, (personal_id,))
            registro = cur.fetchone()

            # Si no existe registro hoy: crear ENTRADA
            if not registro:
                cur.execute("""
                    INSERT INTO asistencias_personal (
                        personal_id, fecha, fecha_dia, hora_entrada, hora_salida, estado_asistencia
                    )
                    VALUES (
                        %s,
                        CURRENT_TIMESTAMP,
                        (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date,
                        CURRENT_TIMESTAMP,
                        NULL,
                        'Asistencia'
                    )
                """, (personal_id,))
                conn.commit()
                cur.close()
                conn.close()

                return jsonify({
                    "success": True,
                    "tipo_registro": "entrada",
                    "message": f"Entrada registrada: {nombre}",
                    "nombre": nombre,
                    "clave": clave,
                    "estado": "Asistencia"
                })

            asistencia_id, estado_actual, hora_entrada, hora_salida = registro

            # Si existe pero no tiene entrada aún
            if hora_entrada is None:
                cur.execute("""
                    UPDATE asistencias_personal
                    SET hora_entrada = CURRENT_TIMESTAMP,
                        estado_asistencia = 'Asistencia',
                        fecha = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (asistencia_id,))
                conn.commit()
                cur.close()
                conn.close()

                return jsonify({
                    "success": True,
                    "tipo_registro": "entrada",
                    "message": f"Entrada registrada: {nombre}",
                    "nombre": nombre,
                    "clave": clave,
                    "estado": "Asistencia"
                })

            # Si ya tiene entrada pero no salida
            if hora_salida is None:
                cur.execute("""
                    UPDATE asistencias_personal
                    SET hora_salida = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (asistencia_id,))
                conn.commit()
                cur.close()
                conn.close()

                return jsonify({
                    "success": True,
                    "tipo_registro": "salida",
                    "message": f"Salida registrada: {nombre}",
                    "nombre": nombre,
                    "clave": clave,
                    "estado": estado_actual
                })

            cur.close()
            conn.close()
            return jsonify({
                "success": False,
                "message": f"Entrada y salida ya registradas hoy para {nombre}",
                "nombre": nombre,
                "clave": clave,
                "estado": estado_actual
            })

        cur.close()
        conn.close()
        return jsonify({
            "success": False,
            "message": "Usuario no encontrado, debe darse de alta primero"
        }), 404

    except Exception as e:
        conn.rollback()
        print("Error al registrar asistencia:", e)
        cur.close()
        conn.close()
        return jsonify({
            "success": False,
            "message": "Error al registrar asistencia"
        }), 500

# ============================
# Avanzar ciclo escolar
# ============================
@app.route("/api/avanzar-grados", methods=["POST"])
def avanzar_grados():
    try:
        conn = conectar_bd()
        cur = conn.cursor()
        # Avanza todos los semestres excepto los que ya están en 6
        cur.execute("""
            UPDATE estudiantes
            SET semestre = semestre + 1
            WHERE semestre < 6
        """)
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True, "message": "Todos los estudiantes fueron avanzados al siguiente semestre"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============================
# Actualizar grado manual
# ============================
@app.route("/api/actualizar-grado", methods=["POST"])
def actualizar_grado():
    try:
        data = request.get_json()
        grado_actual = int(data.get("grado_actual"))
        grado_nuevo = int(data.get("grado_nuevo"))

        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute("""
            UPDATE estudiantes
            SET semestre = %s
            WHERE semestre = %s
        """, (grado_nuevo, grado_actual))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True, "message": f"Los estudiantes de {grado_actual}° fueron actualizados a {grado_nuevo}°"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})




@app.route("/api/qr/<codigo>", methods=["GET"])
def generar_qr(codigo):
    import qrcode, io
    from flask import request, send_file

    # 👉 Usa tu IP local en pruebas
    ip_local = "192.168.0.4"  # reemplaza con tu IPv4 real
    url = f"http://{ip_local}:5000/api/registrar-asistencia?codigo_qr={codigo}"

    # 👉 En producción, cambia la línea anterior por tu dominio público
    # url = f"https://tuservidor.com/api/registrar-asistencia?codigo_qr={codigo}"

    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    # Si viene con ?download=1 → forzar descarga
    if request.args.get("download") == "1":
        return send_file(
            buf,
            mimetype="image/png",
            as_attachment=True,
            download_name=f"qr_{codigo}.png"
        )
    else:
        # Mostrar inline (para <img>)
        return send_file(buf, mimetype="image/png")
@app.route("/api/cargar-estudiantes-excel", methods=["POST"])
def cargar_estudiantes_excel():
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No se envió archivo"}), 400

    file = request.files["file"]

    try:
        # Leer Excel con pandas
        df = pd.read_excel(file)

        # Validar columnas necesarias
        columnas_requeridas = ["matricula", "nombre", "apellido_paterno", "apellido_materno", "carrera", "semestre", "grupo"]
        for col in columnas_requeridas:
            if col not in df.columns:
                return jsonify({"success": False, "message": f"Falta columna: {col}"}), 400

        conn = conectar_bd()
        cur = conn.cursor()

        insertados = 0
        errores = []

        for _, row in df.iterrows():
            try:
                cur.execute("""
                    INSERT INTO estudiantes (matricula, nombre, apellido_paterno, apellido_materno, carrera, semestre, grupo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    str(row["matricula"]).strip(),
                    row["nombre"],
                    row["apellido_paterno"],
                    row["apellido_materno"],
                    row["carrera"],
                    row["semestre"],
                    row["grupo"]
                ))
                insertados += 1
            except Exception as e:
                errores.append({"matricula": row["matricula"], "error": str(e)})

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "insertados": insertados,
            "errores": errores
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": f"Error procesando archivo: {str(e)}"}), 500

@app.route("/verificacion")
def vista_verificacion():
    return render_template("verificación.html")

@app.route("/verificacion-usuarios")
def vista_verificacion_usuarios():
    return render_template("Verificacion_Usuarios.html")


# 🚀 Ejecutar la app
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)




