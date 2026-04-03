from flask import Flask, request, jsonify, render_template, redirect, url_for, session, redirect,send_file
from flask_cors import CORS 
import psycopg2
import pandas as pd
import io
import qrcode
import requests
import bcrypt
from datetime import datetime
from functools import wraps
import threading
import time
import os
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


def ruta_recurso(relativa):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relativa)

app = Flask(
    __name__,
    template_folder=ruta_recurso("templates"),
    static_folder=ruta_recurso("static")
)

CORS(app)
app.secret_key = "cecyteh_verificacion_2026"

#Telegram
BOT_TOKEN = "8662204262:AAHxsA-KeSvid-xaJ3LPWE6Vw1W3Mt2mTJc"
CHAT_ID_ADMIN = "8767812052"
#CHAT_ID_TUTOR_PRUEBA = "1333201682"

#Conexión a la base de datos
def conectar_bd():
    return psycopg2.connect(
        host="localhost",
        database="db_control",
        user="postgres",
        password="12345"
    )

@app.route("/api/reporte_personal/pdf", methods=["GET"])
def exportar_reporte_personal_pdf():
    clave = request.args.get("clave")
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")
    tipo = request.args.get("tipo")

    if not inicio or not fin or not tipo:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        if tipo == "general":
            query = """
                SELECT 
                    p.clave,
                    p.nombre,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.puesto,
                    COUNT(CASE WHEN a.estado_asistencia = 'Asistencia' THEN 1 END) AS asistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Inasistencia' THEN 1 END) AS inasistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Justificación' THEN 1 END) AS justificaciones
                FROM personal p
                LEFT JOIN asistencias_personal a 
                    ON p.id = a.personal_id
                    AND a.fecha >= %s
                    AND a.fecha < %s::date + INTERVAL '1 day'
            """
            params = [inicio, fin]

            if clave:
                query += " WHERE p.clave = %s"
                params.append(clave)

            query += """
                GROUP BY p.clave, p.nombre, p.apellido_paterno, p.apellido_materno, p.puesto
                ORDER BY p.nombre
            """

            cur.execute(query, params)
            resultados = cur.fetchall()

            encabezados = [
                "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                "Puesto", "Fecha Inicio", "Fecha Fin",
                "Asistencias", "Inasistencias", "Justificaciones"
            ]

            filas = [
                [
                    str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]),
                    str(inicio), str(fin), str(r[5]), str(r[6]), str(r[7])
                ]
                for r in resultados
            ]

            titulo = f"Reporte General del Personal ({inicio} a {fin})"
            nombre_archivo = f"reporte_general_personal_{inicio}_a_{fin}.pdf"

        else:
            mapa_estados = {
                "asistencias": "Asistencia",
                "inasistencias": "Inasistencia",
                "justificaciones": "Justificación"
            }

            if tipo not in mapa_estados:
                return jsonify({"success": False, "message": "Tipo de reporte no válido"}), 400

            estado = mapa_estados[tipo]

            query = """
                SELECT
                    p.clave,
                    p.nombre,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.puesto,
                    a.fecha,
                    a.estado_asistencia,
                    a.motivo_justificacion
                FROM asistencias_personal a
                JOIN personal p ON a.personal_id = p.id
                WHERE a.estado_asistencia = %s
                  AND a.fecha >= %s
                  AND a.fecha < %s::date + INTERVAL '1 day'
            """
            params = [estado, inicio, fin]

            if clave:
                query += " AND p.clave = %s"
                params.append(clave)

            query += " ORDER BY a.fecha"

            cur.execute(query, params)
            resultados = cur.fetchall()

            if tipo == "asistencias":
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Asistencia"
                ]

                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]),
                        r[5].strftime("%Y-%m-%d") if r[5] else "",
                        "✔"
                    ]
                    for r in resultados
                ]

            elif tipo == "inasistencias":
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Inasistencia"
                ]

                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]),
                        r[5].strftime("%Y-%m-%d") if r[5] else "",
                        "✘"
                    ]
                    for r in resultados
                ]

            else:  # justificaciones
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Motivo"
                ]

                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]),
                        r[5].strftime("%Y-%m-%d") if r[5] else "",
                        str(r[7]) if r[7] else ""
                    ]
                    for r in resultados
                ]

            titulo = f"Reporte de {estado} del Personal ({inicio} a {fin})"
            nombre_archivo = f"reporte_{tipo}_personal_{inicio}_a_{fin}.pdf"

        if not filas:
            return jsonify({"success": False, "message": "No hay datos para exportar"}), 404

        pdf_buffer = generar_pdf_tabla(titulo, encabezados, filas)

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype="application/pdf"
        )

    except Exception as e:
        print("Error al exportar PDF del personal:", e)
        return jsonify({"success": False, "message": "Error al generar PDF"}), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/reporte_estudiantes/pdf", methods=["GET"])
def exportar_reporte_estudiantes_pdf():
    matricula = request.args.get("matricula")
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")
    tipo = request.args.get("tipo")

    if not inicio or not fin or not tipo:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        if tipo == "general":
            query = """
                SELECT 
                    e.matricula,
                    e.nombre,
                    e.apellido_paterno,
                    e.apellido_materno,
                    e.carrera,
                    e.semestre,
                    e.grupo,
                    COUNT(CASE WHEN a.estado_asistencia = 'Asistencia' THEN 1 END) AS asistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Inasistencia' THEN 1 END) AS inasistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Justificación' THEN 1 END) AS justificaciones
                FROM estudiantes e
                LEFT JOIN asistencias a 
                    ON e.matricula = a.matricula
                    AND a.fecha >= %s
                    AND a.fecha < %s::date + INTERVAL '1 day'
            """
            params = [inicio, fin]

            if matricula:
                query += " WHERE e.matricula = %s"
                params.append(matricula)

            query += """
                GROUP BY e.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                         e.carrera, e.semestre, e.grupo
                ORDER BY e.nombre
            """

            cur.execute(query, params)
            resultados = cur.fetchall()

            encabezados = [
                "Matrícula", "Nombre", "Apellido Paterno", "Apellido Materno",
                "Carrera", "Semestre", "Grupo",
                "Asistencias", "Inasistencias", "Justificaciones"
            ]

            filas = [
                [
                    str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                    str(r[4]), str(r[5]), str(r[6]),
                    str(r[7]), str(r[8]), str(r[9])
                ]
                for r in resultados
            ]

            titulo = f"Reporte General de Estudiantes ({inicio} a {fin})"
            nombre_archivo = f"reporte_general_estudiantes_{inicio}_a_{fin}.pdf"

        else:
            mapa_estados = {
                "asistencias": "Asistencia",
                "inasistencias": "Inasistencia",
                "justificaciones": "Justificación"
            }

            if tipo not in mapa_estados:
                return jsonify({"success": False, "message": "Tipo de reporte no válido"}), 400

            estado = mapa_estados[tipo]

            query = """
                SELECT
                    e.matricula,
                    e.nombre,
                    e.apellido_paterno,
                    e.apellido_materno,
                    e.carrera,
                    e.semestre,
                    e.grupo,
                    a.fecha,
                    a.estado_asistencia,
                    a.motivo_justificacion
                FROM asistencias a
                JOIN estudiantes e ON a.matricula = e.matricula
                WHERE a.estado_asistencia = %s
                  AND a.fecha >= %s
                  AND a.fecha < %s::date + INTERVAL '1 day'
            """
            params = [estado, inicio, fin]

            if matricula:
                query += " AND e.matricula = %s"
                params.append(matricula)

            query += " ORDER BY a.fecha"

            cur.execute(query, params)
            resultados = cur.fetchall()

            if tipo == "asistencias":
                encabezados = [
                    "Matrícula", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Carrera", "Semestre", "Grupo", "Fecha", "Asistencia"
                ]

                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]), str(r[5]), str(r[6]),
                        r[7].strftime("%Y-%m-%d") if r[7] else "",
                        "✔"
                    ]
                    for r in resultados
                ]

            elif tipo == "inasistencias":
                encabezados = [
                    "Matrícula", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Carrera", "Semestre", "Grupo", "Fecha", "Inasistencia"
                ]

                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]), str(r[5]), str(r[6]),
                        r[7].strftime("%Y-%m-%d") if r[7] else "",
                        "✘"
                    ]
                    for r in resultados
                ]

            else:  # justificaciones
                encabezados = [
                    "Matrícula", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Carrera", "Semestre", "Grupo", "Fecha", "Motivo"
                ]

                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]), str(r[5]), str(r[6]),
                        r[7].strftime("%Y-%m-%d") if r[7] else "",
                        str(r[9]) if r[9] else ""
                    ]
                    for r in resultados
                ]

            titulo = f"Reporte de {estado} de Estudiantes ({inicio} a {fin})"
            nombre_archivo = f"reporte_{tipo}_estudiantes_{inicio}_a_{fin}.pdf"

        if not filas:
            return jsonify({"success": False, "message": "No hay datos para exportar"}), 404

        pdf_buffer = generar_pdf_tabla(titulo, encabezados, filas)

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype="application/pdf"
        )

    except Exception as e:
        print("Error al exportar PDF de estudiantes:", e)
        return jsonify({"success": False, "message": "Error al generar PDF"}), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/reporte_grupal_estudiantes/pdf", methods=["GET"])
def exportar_reporte_grupal_estudiantes_pdf():
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")
    carrera = request.args.get("carrera")
    semestre = request.args.get("semestre")
    grupo = request.args.get("grupo")
    tipo = request.args.get("tipo")

    if not inicio or not fin or not carrera or not semestre or not grupo or not tipo:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        if tipo == "general":
            query = """
                SELECT
                    e.matricula,
                    e.nombre,
                    e.apellido_paterno,
                    e.apellido_materno,
                    e.carrera,
                    e.semestre,
                    e.grupo,
                    COUNT(CASE WHEN a.estado_asistencia = 'Asistencia' THEN 1 END) AS asistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Inasistencia' THEN 1 END) AS inasistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Justificación' THEN 1 END) AS justificaciones
                FROM estudiantes e
                LEFT JOIN asistencias a
                    ON e.matricula = a.matricula
                    AND a.fecha >= %s
                    AND a.fecha < %s::date + INTERVAL '1 day'
                WHERE e.carrera = %s
                  AND e.semestre = %s
                  AND e.grupo = %s
                GROUP BY e.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                         e.carrera, e.semestre, e.grupo
                ORDER BY e.nombre
            """
            params = [inicio, fin, carrera, semestre, grupo]
            cur.execute(query, params)
            resultados = cur.fetchall()

            encabezados = [
                "Matrícula", "Nombre", "Apellido Paterno", "Apellido Materno",
                "Carrera", "Semestre", "Grupo",
                "Asistencias", "Inasistencias", "Justificaciones"
            ]

            filas = [
                [
                    str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                    str(r[4]), str(r[5]), str(r[6]),
                    str(r[7]), str(r[8]), str(r[9])
                ]
                for r in resultados
            ]

            titulo = f"Reporte Grupal General de Estudiantes ({inicio} a {fin})"
            nombre_archivo = f"reporte_grupal_estudiantes_general_{inicio}_a_{fin}.pdf"

        else:
            mapa_estados = {
                "asistencias": "Asistencia",
                "inasistencias": "Inasistencia",
                "justificaciones": "Justificación"
            }

            if tipo not in mapa_estados:
                return jsonify({"success": False, "message": "Tipo no válido"}), 400

            estado = mapa_estados[tipo]

            query = """
                SELECT
                    e.matricula,
                    e.nombre,
                    e.apellido_paterno,
                    e.apellido_materno,
                    e.carrera,
                    e.semestre,
                    e.grupo,
                    a.fecha,
                    a.motivo_justificacion
                FROM asistencias a
                JOIN estudiantes e ON a.matricula = e.matricula
                WHERE a.estado_asistencia = %s
                  AND a.fecha >= %s
                  AND a.fecha < %s::date + INTERVAL '1 day'
                  AND e.carrera = %s
                  AND e.semestre = %s
                  AND e.grupo = %s
                ORDER BY a.fecha
            """
            params = [estado, inicio, fin, carrera, semestre, grupo]
            cur.execute(query, params)
            resultados = cur.fetchall()

            if tipo == "asistencias":
                encabezados = [
                    "Matrícula", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Carrera", "Semestre", "Grupo", "Fecha", "Asistencia"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]), str(r[5]), str(r[6]),
                        r[7].strftime("%Y-%m-%d %H:%M") if r[7] else "",
                        "✔"
                    ]
                    for r in resultados
                ]

            elif tipo == "inasistencias":
                encabezados = [
                    "Matrícula", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Carrera", "Semestre", "Grupo", "Fecha", "Inasistencia"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]), str(r[5]), str(r[6]),
                        r[7].strftime("%Y-%m-%d %H:%M") if r[7] else "",
                        "✘"
                    ]
                    for r in resultados
                ]

            else:  # justificaciones
                encabezados = [
                    "Matrícula", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Carrera", "Semestre", "Grupo", "Fecha", "Motivo"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]), str(r[5]), str(r[6]),
                        r[7].strftime("%Y-%m-%d %H:%M") if r[7] else "",
                        str(r[8]) if r[8] else ""
                    ]
                    for r in resultados
                ]

            titulo = f"Reporte Grupal de {estado} de Estudiantes ({inicio} a {fin})"
            nombre_archivo = f"reporte_grupal_estudiantes_{tipo}_{inicio}_a_{fin}.pdf"

        if not filas:
            return jsonify({"success": False, "message": "No hay datos para exportar"}), 404

        pdf_buffer = generar_pdf_tabla(titulo, encabezados, filas)

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype="application/pdf"
        )

    except Exception as e:
        print("Error al exportar PDF grupal de estudiantes:", e)
        return jsonify({"success": False, "message": "Error al generar PDF"}), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/reporte_grupal_docentes/pdf", methods=["GET"])
def exportar_reporte_grupal_docentes_pdf():
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")
    tipo = request.args.get("tipo")

    if not inicio or not fin or not tipo:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        if tipo == "general":
            query = """
                SELECT
                    p.clave,
                    p.nombre,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.puesto,
                    COUNT(CASE WHEN a.estado_asistencia = 'Asistencia' THEN 1 END) AS asistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Inasistencia' THEN 1 END) AS inasistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Justificación' THEN 1 END) AS justificaciones
                FROM personal p
                LEFT JOIN asistencias_personal a
                    ON p.id = a.personal_id
                    AND a.fecha >= %s
                    AND a.fecha < %s::date + INTERVAL '1 day'
                WHERE LOWER(p.puesto) LIKE %s
                GROUP BY p.clave, p.nombre, p.apellido_paterno, p.apellido_materno, p.puesto
                ORDER BY p.nombre
            """
            params = [inicio, fin, "%docente%"]
            cur.execute(query, params)
            resultados = cur.fetchall()

            encabezados = [
                "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                "Puesto", "Asistencias", "Inasistencias", "Justificaciones"
            ]

            filas = [
                [
                    str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                    str(r[4]), str(r[5]), str(r[6]), str(r[7])
                ]
                for r in resultados
            ]

            titulo = f"Reporte Grupal General de Docentes ({inicio} a {fin})"
            nombre_archivo = f"reporte_grupal_docentes_general_{inicio}_a_{fin}.pdf"

        else:
            mapa_estados = {
                "asistencias": "Asistencia",
                "inasistencias": "Inasistencia",
                "justificaciones": "Justificación"
            }

            if tipo not in mapa_estados:
                return jsonify({"success": False, "message": "Tipo no válido"}), 400

            estado = mapa_estados[tipo]

            query = """
                SELECT
                    p.clave,
                    p.nombre,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.puesto,
                    a.fecha,
                    a.motivo_justificacion
                FROM asistencias_personal a
                JOIN personal p ON a.personal_id = p.id
                WHERE a.estado_asistencia = %s
                  AND a.fecha >= %s
                  AND a.fecha < %s::date + INTERVAL '1 day'
                  AND LOWER(p.puesto) LIKE %s
                ORDER BY a.fecha
            """
            params = [estado, inicio, fin, "%docente%"]
            cur.execute(query, params)
            resultados = cur.fetchall()

            if tipo == "asistencias":
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Asistencia"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]),
                        r[5].strftime("%Y-%m-%d %H:%M") if r[5] else "",
                        "✔"
                    ]
                    for r in resultados
                ]

            elif tipo == "inasistencias":
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Inasistencia"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]),
                        r[5].strftime("%Y-%m-%d %H:%M") if r[5] else "",
                        "✘"
                    ]
                    for r in resultados
                ]

            else:  # justificaciones
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Motivo"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]),
                        r[5].strftime("%Y-%m-%d %H:%M") if r[5] else "",
                        str(r[6]) if r[6] else ""
                    ]
                    for r in resultados
                ]

            titulo = f"Reporte Grupal de {estado} de Docentes ({inicio} a {fin})"
            nombre_archivo = f"reporte_grupal_docentes_{tipo}_{inicio}_a_{fin}.pdf"

        if not filas:
            return jsonify({"success": False, "message": "No hay datos para exportar"}), 404

        pdf_buffer = generar_pdf_tabla(titulo, encabezados, filas)

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype="application/pdf"
        )

    except Exception as e:
        print("Error al exportar PDF grupal de docentes:", e)
        return jsonify({"success": False, "message": "Error al generar PDF"}), 500

    finally:
        cur.close()
        conn.close()
@app.route("/api/reporte_grupal_administrativo/pdf", methods=["GET"])
def exportar_reporte_grupal_administrativo_pdf():
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")
    tipo = request.args.get("tipo")

    if not inicio or not fin or not tipo:
        return jsonify({"success": False, "message": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        if tipo == "general":
            query = """
                SELECT
                    p.clave,
                    p.nombre,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.puesto,
                    COUNT(CASE WHEN a.estado_asistencia = 'Asistencia' THEN 1 END) AS asistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Inasistencia' THEN 1 END) AS inasistencias,
                    COUNT(CASE WHEN a.estado_asistencia = 'Justificación' THEN 1 END) AS justificaciones
                FROM personal p
                LEFT JOIN asistencias_personal a
                    ON p.id = a.personal_id
                    AND a.fecha >= %s
                    AND a.fecha < %s::date + INTERVAL '1 day'
                WHERE LOWER(p.puesto) NOT LIKE %s
                GROUP BY p.clave, p.nombre, p.apellido_paterno, p.apellido_materno, p.puesto
                ORDER BY p.nombre
            """
            params = [inicio, fin, "%docente%"]
            cur.execute(query, params)
            resultados = cur.fetchall()

            encabezados = [
                "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                "Puesto", "Asistencias", "Inasistencias", "Justificaciones"
            ]

            filas = [
                [
                    str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                    str(r[4]), str(r[5]), str(r[6]), str(r[7])
                ]
                for r in resultados
            ]

            titulo = f"Reporte Grupal General de Personal Administrativo ({inicio} a {fin})"
            nombre_archivo = f"reporte_grupal_administrativo_general_{inicio}_a_{fin}.pdf"

        else:
            mapa_estados = {
                "asistencias": "Asistencia",
                "inasistencias": "Inasistencia",
                "justificaciones": "Justificación"
            }

            if tipo not in mapa_estados:
                return jsonify({"success": False, "message": "Tipo no válido"}), 400

            estado = mapa_estados[tipo]

            query = """
                SELECT
                    p.clave,
                    p.nombre,
                    p.apellido_paterno,
                    p.apellido_materno,
                    p.puesto,
                    a.fecha,
                    a.motivo_justificacion
                FROM asistencias_personal a
                JOIN personal p ON a.personal_id = p.id
                WHERE a.estado_asistencia = %s
                  AND a.fecha >= %s
                  AND a.fecha < %s::date + INTERVAL '1 day'
                  AND LOWER(p.puesto) NOT LIKE %s
                ORDER BY a.fecha
            """
            params = [estado, inicio, fin, "%docente%"]
            cur.execute(query, params)
            resultados = cur.fetchall()

            if tipo == "asistencias":
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Asistencia"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]),
                        r[5].strftime("%Y-%m-%d %H:%M") if r[5] else "",
                        "✔"
                    ]
                    for r in resultados
                ]

            elif tipo == "inasistencias":
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Inasistencia"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]),
                        r[5].strftime("%Y-%m-%d %H:%M") if r[5] else "",
                        "✘"
                    ]
                    for r in resultados
                ]

            else:  # justificaciones
                encabezados = [
                    "Clave", "Nombre", "Apellido Paterno", "Apellido Materno",
                    "Puesto", "Fecha", "Motivo"
                ]
                filas = [
                    [
                        str(r[0]), str(r[1]), str(r[2]), str(r[3]),
                        str(r[4]),
                        r[5].strftime("%Y-%m-%d %H:%M") if r[5] else "",
                        str(r[6]) if r[6] else ""
                    ]
                    for r in resultados
                ]

            titulo = f"Reporte Grupal de {estado} de Personal Administrativo ({inicio} a {fin})"
            nombre_archivo = f"reporte_grupal_administrativo_{tipo}_{inicio}_a_{fin}.pdf"

        if not filas:
            return jsonify({"success": False, "message": "No hay datos para exportar"}), 404

        pdf_buffer = generar_pdf_tabla(titulo, encabezados, filas)

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype="application/pdf"
        )

    except Exception as e:
        print("Error al exportar PDF grupal administrativo:", e)
        return jsonify({"success": False, "message": "Error al generar PDF"}), 500

    finally:
        cur.close()
        conn.close()

def generar_pdf_tabla(titulo, encabezados, filas):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    elementos = []
    estilos = getSampleStyleSheet()

    elementos.append(Paragraph(titulo, estilos["Title"]))
    elementos.append(Spacer(1, 12))

    data = [encabezados] + filas

    tabla = Table(data, repeatRows=1)

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#198754")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elementos.append(tabla)
    doc.build(elementos)

    buffer.seek(0)
    return buffer

def login_requerido(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if not session.get("usuario_autenticado"):
            return redirect(url_for("login_vista"))
        return f(*args, **kwargs)
    return decorada


def verificacion_requerida(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if not session.get("verificacion_autorizada"):
            return redirect(url_for("acceso_verificacion"))
        return f(*args, **kwargs)
    return decorada

@app.route("/acceso-verificacion")
def acceso_verificacion():
    return render_template("acceso_verificacion.html")

def obtener_mensajes_telegram():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

    try:
        response = requests.get(url, timeout=5)
        data = response.json()

        mensajes = []

        if data.get("ok"):
            for item in data.get("result", []):
                if "message" in item:
                    mensaje = item["message"]

                    chat_id = mensaje["chat"]["id"]
                    texto = mensaje.get("text", "").strip()

                    mensajes.append({
                        "chat_id": str(chat_id),
                        "texto": texto
                    })

        return mensajes

    except Exception as e:
        print("Error al obtener mensajes:", e)
        return []

@app.route("/api/chat_ids", methods=["GET"])
def api_chat_ids():
    mensajes = obtener_mensajes_telegram()
    return jsonify({
        "success": True,
        "datos": mensajes
    }), 200

@app.route("/api/sincronizar-chat-ids", methods=["GET", "POST"])
def api_sincronizar_chat_ids():
    resultado = sincronizar_chat_ids_telegram()
    return jsonify(resultado), 200


def sincronizar_chat_ids_telegram():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()

        # Obtener último update_id guardado
        cursor.execute("SELECT ultimo_update_id FROM telegram_control LIMIT 1")
        fila = cursor.fetchone()
        ultimo_update_id = fila[0] if fila else 0

        # Pedir solo mensajes nuevos
        params_telegram = {
            "offset": ultimo_update_id + 1,
            "timeout": 2
        }

        response = requests.get(url, params=params_telegram, timeout=5)
        data = response.json()

        actualizados = 0
        nuevo_update_id = ultimo_update_id

        if data.get("ok"):
            for item in data.get("result", []):
                update_id = item["update_id"]
                mensaje = item.get("message", {})
                chat_id = mensaje.get("chat", {}).get("id")
                texto = mensaje.get("text", "").strip()

                if not chat_id or not texto:
                    if update_id > nuevo_update_id:
                        nuevo_update_id = update_id
                    continue

                partes = texto.split()

                # 🔹 CASO 1: SOLO /start
                if texto.lower() == "/start":
                    enviar_mensaje_telegram(
                        chat_id,
                        "👋 Bienvenido al sistema de asistencias.\n\n"
                        "Usa:\n/start TU_MATRICULA\n\n"
                        "También puedes usar:\n"
                        "/info\n"
                        "/estado"
                    )

                # 🔹 CASO 2: /start MATRICULA
                elif len(partes) >= 2 and partes[0].lower() == "/start":
                    matricula = partes[1].strip()

                    cursor.execute("""
                        SELECT nombre, apellido_paterno, apellido_materno
                        FROM estudiantes
                        WHERE matricula = %s
                    """, (matricula,))
                    alumno = cursor.fetchone()

                    if alumno:
                        nombre = alumno[0]
                        apellido_paterno = alumno[1]
                        apellido_materno = alumno[2]

                        cursor.execute("""
                            UPDATE estudiantes
                            SET chat_id_telegram = %s
                            WHERE matricula = %s
                        """, (str(chat_id), matricula))

                        actualizados += 1

                        enviar_mensaje_telegram(
                            chat_id,
                            f"✅ Hola {nombre} {apellido_paterno} {apellido_materno}, "
                            f"tu matrícula {matricula} ha sido vinculada."
                        )
                    else:
                        enviar_mensaje_telegram(
                            chat_id,
                            f"❌ No se encontró la matrícula {matricula}."
                        )

                # 🔹 CASO 3: /info
                elif texto.lower() == "/info":
                    enviar_mensaje_telegram(
                        chat_id,
                        "ℹ️ Bot de asistencias activo.\n\n"
                        "Comandos disponibles:\n"
                        "/start TU_MATRICULA → vincular matrícula\n"
                        "/info → ver ayuda\n"
                        "/estado → verificar estado del chat"
                    )

                # 🔹 CASO 4: /estado
                elif texto.lower() == "/estado":
                    enviar_mensaje_telegram(
                        chat_id,
                        "✅ Tu chat está activo.\n\n"
                        "Si ya vinculaste tu matrícula, recibirás notificaciones automáticas."
                    )

                # 🔹 CASO 5: OTRO TEXTO
                else:
                    enviar_mensaje_telegram(
                        chat_id,
                        "⚠️ Comando no reconocido.\n\n"
                        "Usa alguno de estos:\n"
                        "/start TU_MATRICULA\n"
                        "/info\n"
                        "/estado"
                    )

                if update_id > nuevo_update_id:
                    nuevo_update_id = update_id

        # Guardar último update_id
        cursor.execute("""
            UPDATE telegram_control
            SET ultimo_update_id = %s
        """, (nuevo_update_id,))

        conexion.commit()
        cursor.close()
        conexion.close()

        return {
            "success": True,
            "actualizados": actualizados
        }

    except Exception as e:
        print("Error:", e)
        return {
            "success": False,
            "message": str(e)
        }

def enviar_mensaje_telegram(chat_id, texto):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": texto
    }

    try:
        response = requests.post(url, data=payload, timeout=5)
        return response.json()
    except Exception as e:
        print("Error al enviar mensaje por Telegram:", e)
        return None

@app.route("/api/login-verificacion", methods=["POST"])
def login_verificacion():
    data = request.get_json(silent=True) or {}
    usuario = data.get("usuario")
    contraseña = data.get("contraseña")

    print("DEBUG login_verificacion -> data:", data)
    print("DEBUG login_verificacion -> usuario:", usuario)

    if not usuario or not contraseña:
        return jsonify({"success": False, "message": "Faltan credenciales"}), 400

    conn = None
    cur = None

    try:
        conn = conectar_bd()
        cur = conn.cursor()

        cur.execute("""
            SELECT rol, es_maestro, contraseña
            FROM usuarios
            WHERE usuario = %s
        """, (usuario,))

        resultado = cur.fetchone()
        print("DEBUG login_verificacion -> resultado:", resultado)

        if not resultado:
            return jsonify({"success": False, "message": "Credenciales incorrectas"}), 401

        rol = resultado[0]
        es_maestro = resultado[1]
        hash_guardado = resultado[2]

        print("DEBUG login_verificacion -> rol:", rol)
        print("DEBUG login_verificacion -> es_maestro:", es_maestro)

        if not verificar_contrasena(contraseña, hash_guardado):
            return jsonify({"success": False, "message": "Credenciales incorrectas"}), 401

        if rol == "admin" or es_maestro:
            session["verificacion_autorizada"] = True
            session["usuario_verificacion"] = usuario

            return jsonify({
                "success": True,
                "message": "Acceso autorizado"
            }), 200

        return jsonify({
            "success": False,
            "message": "No tienes permisos para acceder a este módulo"
        }), 403

    except Exception as e:
        print("ERROR login_verificacion:", repr(e))
        return jsonify({"success": False, "message": f"Error al validar acceso: {str(e)}"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def enviar_telegram(mensaje, chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print("Error al enviar mensaje a Telegram:", e)
        return False
    
def enviar_telegram_multiple(mensaje, chat_ids):
    enviados = []

    for chat_id in chat_ids:
        if chat_id and str(chat_id).strip():
            ok = enviar_telegram(mensaje, str(chat_id).strip())
            enviados.append({
                "chat_id": str(chat_id).strip(),
                "enviado": ok
            })

    return enviados

def ciclo_telegram():
    while True:
        try:
            resultado = sincronizar_chat_ids_telegram()
            if resultado.get("success"):
                actualizados = resultado.get("actualizados", 0)
                if actualizados > 0:
                    print(f"Telegram sincronizado. Actualizados: {actualizados}")
            else:
                print("Error en sincronización Telegram:", resultado.get("message"))
        except Exception as e:
            print("Error en ciclo_telegram:", e)

        time.sleep(5)  # revisa cada 5 segundos

def encriptar_contrasena(contraseña):
    return bcrypt.hashpw(contraseña.encode('utf-8'), 
    bcrypt.gensalt()).decode('utf-8')
def verificar_contrasena(contrasena_ingresada, hash_guardada):
    return bcrypt.checkpw(contrasena_ingresada.encode('utf-8'), 
    hash_guardada.encode('utf-8'))


@app.route("/api/modificar-reporte")
def modificar_reporte():
    matricula = request.args.get("matricula")
    inicio = request.args.get("inicio")
    fin = request.args.get("fin")

    if not matricula or not inicio or not fin:
        return jsonify({"error": "Faltan parámetros"}), 400

    conn = conectar_bd()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT 
                a.id,
                a.matricula,
                e.nombre,
                e.apellido_paterno,
                e.apellido_materno,
                e.carrera,
                e.semestre,
                e.grupo,
                a.fecha_dia,
                a.estado_asistencia,
                a.motivo_justificacion
            FROM asistencias a
            JOIN estudiantes e ON a.matricula = e.matricula
            WHERE a.matricula = %s
              AND a.fecha >= %s
              AND a.fecha < %s::date + INTERVAL '1 day'
            ORDER BY a.fecha
        """, (matricula, inicio, fin))

        resultados = cursor.fetchall()
        registros = []

        for r in resultados:
            registros.append({
                "id": r[0],
                "matricula": r[1],
                "nombre": r[2],
                "apellido_paterno": r[3],
                "apellido_materno": r[4],
                "carrera": r[5],
                "semestre": r[6],
                "grupo": r[7],
                "fecha": r[8].strftime("%Y-%m-%d") if r[8] else "",
                "estado_asistencia": r[9],
                "motivo_justificacion": r[10]
            })

        return jsonify(registros)

    except Exception as e:
        print("Error en /api/modificar-reporte:", e)
        return jsonify({"error": "Error al obtener registros"}), 500

    finally:
        cursor.close()
        conn.close()

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

@app.route("/api/eliminar_estudiante", methods=["POST"])
def eliminar_estudiante():
    data = request.get_json()
    matricula = data.get("matricula")

    if not matricula:
        return jsonify({
            "success": False,
            "message": "Falta la matrícula"
        }), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM estudiantes
            WHERE matricula = %s
        """, (matricula,))

        conn.commit()

        if cur.rowcount > 0:
            return jsonify({
                "success": True,
                "message": "Estudiante eliminado correctamente"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "No se encontró el estudiante"
            }), 404

    except Exception as e:
        conn.rollback()
        print("Error al eliminar estudiante:", e)
        return jsonify({
            "success": False,
            "message": "Error al eliminar estudiante"
        }), 500

    finally:
        cur.close()
        conn.close()

# 🗑️ Eliminar un registro
@app.route('/api/eliminar-registro', methods=['POST'])
def eliminar_registro():
    data = request.get_json() or {}
    asistencia_id = data.get("id")

    if not asistencia_id:
        return jsonify({"success": False, "message": "Falta el ID del registro"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM asistencias
            WHERE id = %s
        """, (asistencia_id,))

        conn.commit()

        if cur.rowcount > 0:
            return jsonify({
                "success": True,
                "message": "Registro eliminado correctamente"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "No se encontró el registro"
            }), 404

    except Exception as e:
        conn.rollback()
        print("Error al eliminar registro:", e)
        return jsonify({
            "success": False,
            "message": "Error al eliminar registro"
        }), 500

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

            query += """
                GROUP BY a.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                         e.carrera, e.semestre, e.grupo
                ORDER BY e.nombre
            """

        elif tipo in ["asistencias", "inasistencias", "justificaciones"]:
            estado = {
                "asistencias": "Asistencia",
                "inasistencias": "Inasistencia",
                "justificaciones": "Justificación"
            }[tipo]

            query = """
                SELECT a.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                       e.carrera, e.semestre, e.grupo, a.fecha, a.motivo_justificacion
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
                "fecha": r[7].strftime("%Y-%m-%d"),
                "motivo_justificacion": r[8]
            } for r in resultados]

        return jsonify(registros)

    except Exception as e:
        print("Error al generar reporte:", e)
        return jsonify({"error": "Error al generar reporte"}), 500

    finally:
        cursor.close()
        conn.close()
        
@app.route("/agregar")
@login_requerido
def vista_agregar_estudiante():
    return render_template("agregar.html")

@app.route('/api/agregar_estudiante', methods=['POST'])
def agregar_estudiante():
    data = request.get_json()

    matricula = data.get("matricula")
    nombre = data.get("nombre")
    apellido_paterno = data.get("apellido_paterno")
    apellido_materno = data.get("apellido_materno")
    carrera = data.get("carrera")
    semestre = data.get("semestre")
    grupo = data.get("grupo")
    chat_id_telegram = data.get("chat_id_telegram")

    if chat_id_telegram == "":
        chat_id_telegram = None

    if chat_id_telegram is not None and not str(chat_id_telegram).isdigit():
        return jsonify({"success": False, "message": "El Chat ID de Telegram debe contener solo números"}), 400

    if not all([matricula, nombre, apellido_paterno, apellido_materno, carrera, semestre, grupo]):
        return jsonify({"success": False, "message": "Faltan datos obligatorios"}), 400
    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO estudiantes (
                matricula, nombre, apellido_paterno, apellido_materno,
                carrera, semestre, grupo, chat_id_telegram
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            matricula, nombre, apellido_paterno, apellido_materno,
            carrera, semestre, grupo, chat_id_telegram
        ))

        conn.commit()
        return jsonify({"success": True, "message": "Estudiante agregado correctamente"}), 201

    except Exception as e:
        conn.rollback()
        print("Error al insertar estudiante:", e)
        return jsonify({"success": False, "message": "Error al insertar en la base de datos"}), 500

    finally:
        cur.close()
        conn.close()

@app.route('/api/actualizar_estudiante', methods=['PUT'])
def actualizar_estudiante():
    data = request.get_json() or {}
    matricula = data.get("matricula")

    if not matricula:
        return jsonify({"success": False, "message": "Falta la matrícula"}), 400

    chat_id_telegram = data.get("chat_id_telegram")
    if chat_id_telegram == "":
        chat_id_telegram = None
    if chat_id_telegram is not None and not str(chat_id_telegram).isdigit():
        return jsonify({"success": False, "message": "El Chat ID de Telegram debe contener solo números"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE estudiantes
            SET nombre=%s,
                apellido_paterno=%s,
                apellido_materno=%s,
                carrera=%s,
                semestre=%s,
                grupo=%s,
                chat_id_telegram=%s
            WHERE matricula=%s
        """, (
            data.get("nombre"),
            data.get("apellido_paterno"),
            data.get("apellido_materno"),
            data.get("carrera"),
            data.get("semestre"),
            data.get("grupo"),
            chat_id_telegram,
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
    data = request.get_json() or {}
    usuario = data.get("usuario")
    contraseña = data.get("contraseña")

    if not usuario or not contraseña:
        return jsonify({"success": False, "message": "Faltan credenciales"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, nombre, apellido_paterno, apellido_materno, rol, es_maestro, contraseña
            FROM usuarios
            WHERE usuario = %s
        """, (usuario,))

        resultado = cur.fetchone()

        if resultado and verificar_contrasena(contraseña, resultado[6]):
            session["usuario_autenticado"] = True
            session["usuario"] = usuario
            session["rol"] = resultado[4]
            session["es_maestro"] = resultado[5]

            return jsonify({
                "success": True,
                "usuario": usuario,
                "rol": resultado[4],
                "es_maestro": resultado[5]
            }), 200

        return jsonify({
            "success": False,
            "message": "Credenciales incorrectas"
        }), 401

    except Exception as e:
        print("Error en login:", e)
        return jsonify({
            "success": False,
            "message": "Error al iniciar sesión"
        }), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/validar-master", methods=["POST"])
def validar_master():
    data = request.get_json() or {}
    usuario = data.get("usuario")
    contraseña = data.get("contraseña")

    if not usuario or not contraseña:
        return jsonify({"success": False, "message": "Faltan credenciales"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT es_maestro, contraseña
            FROM usuarios
            WHERE usuario = %s
        """, (usuario,))
        resultado = cur.fetchone()

        if not resultado:
            return jsonify({"success": False, "message": "Credenciales incorrectas"}), 401

        es_maestro = resultado[0]
        hash_guardado = resultado[1]

        if es_maestro and verificar_contrasena(contraseña, hash_guardado):
            return jsonify({"success": True, "message": "Acceso autorizado"}), 200
        else:
            return jsonify({"success": False, "message": "Credenciales incorrectas"}), 401

    except Exception as e:
        print("Error al validar master:", e)
        return jsonify({"success": False, "message": "Error en el servidor"}), 500

    finally:
        cur.close()
        conn.close()


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


@app.route("/api/generar-inasistencias", methods=["POST"])
def generar_inasistencias():
    conn = conectar_bd()
    cur = conn.cursor()

    try:
        # =========================
        # OBTENER ALUMNOS QUE QUEDARÁN CON INASISTENCIA
        # =========================
        cur.execute("""
            SELECT 
                e.matricula,
                e.nombre,
                e.apellido_paterno,
                e.apellido_materno,
                e.chat_id_telegram
            FROM estudiantes e
            WHERE NOT EXISTS (
                SELECT 1
                FROM asistencias a
                WHERE a.matricula = e.matricula
                  AND a.fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            )
        """)
        alumnos_faltantes = cur.fetchall()

        # =========================
        # INSERTAR INASISTENCIAS ALUMNOS
        # =========================
        cur.execute("""
            INSERT INTO asistencias (
                matricula, fecha, fecha_dia, hora_entrada, hora_salida, estado_asistencia
            )
            SELECT 
                e.matricula,
                CURRENT_TIMESTAMP,
                (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date,
                NULL,
                NULL,
                'Inasistencia'
            FROM estudiantes e
            WHERE NOT EXISTS (
                SELECT 1
                FROM asistencias a
                WHERE a.matricula = e.matricula
                  AND a.fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            )
        """)

        alumnos_insertados = cur.rowcount

        # =========================
        # OBTENER PERSONAL QUE QUEDARÁ CON INASISTENCIA
        # =========================
        cur.execute("""
            SELECT 
                p.id,
                p.clave,
                p.nombre,
                p.apellido_paterno,
                p.apellido_materno
            FROM personal p
            WHERE NOT EXISTS (
                SELECT 1
                FROM asistencias_personal ap
                WHERE ap.personal_id = p.id
                  AND ap.fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            )
        """)
        personal_faltante = cur.fetchall()

        # =========================
        # INSERTAR INASISTENCIAS PERSONAL
        # =========================
        cur.execute("""
            INSERT INTO asistencias_personal (
                personal_id, fecha, fecha_dia, hora_entrada, hora_salida, estado_asistencia
            )
            SELECT 
                p.id,
                CURRENT_TIMESTAMP,
                (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date,
                NULL,
                NULL,
                'Inasistencia'
            FROM personal p
            WHERE NOT EXISTS (
                SELECT 1
                FROM asistencias_personal ap
                WHERE ap.personal_id = p.id
                  AND ap.fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            )
        """)

        personal_insertado = cur.rowcount

        conn.commit()

        # =========================
        # ENVIAR MENSAJES TELEGRAM A TUTORES DE ALUMNOS
        # =========================
        fecha_hoy = datetime.now().strftime("%d/%m/%Y")

        for alumno in alumnos_faltantes:
            matricula = alumno[0]
            nombre = alumno[1]
            apellido_paterno = alumno[2]
            apellido_materno = alumno[3]
            chat_id = alumno[4]

            if chat_id:
                enviar_mensaje_telegram(
                    chat_id,
                    f"⚠️ Inasistencia detectada\n\n"
                    f"Alumno: {nombre} {apellido_paterno} {apellido_materno}\n"
                    f"Matrícula: {matricula}\n"
                    f"Fecha: {fecha_hoy}\n\n"
                    f"No se registró asistencia en el sistema."
                )

        return jsonify({
            "success": True,
            "message": "Inasistencias generadas correctamente",
            "alumnos_insertados": alumnos_insertados,
            "personal_insertado": personal_insertado
        }), 200

    except Exception as e:
        conn.rollback()
        print("Error al generar inasistencias:", e)
        return jsonify({
            "success": False,
            "message": "Error al generar inasistencias"
        }), 500

    finally:
        cur.close()
        conn.close()


@app.route("/api/listar_estudiantes", methods=["GET"])
def listar_estudiantes():
    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT matricula, nombre, apellido_paterno, apellido_materno,
                   carrera, semestre, grupo, chat_id_telegram
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
            "grupo": est[6],
            "chat_id_telegram": est[7]
        } for est in estudiantes]

        return jsonify({"success": True, "estudiantes": resultado}), 200

    except Exception as e:
        print("Error al listar estudiantes:", e)
        return jsonify({"success": False, "message": "Error al obtener estudiantes"}), 500

    finally:
        cur.close()
        conn.close()

@app.route('/api/registrar_usuario', methods=['POST'])
@login_requerido
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
        contraseña_encriptada = encriptar_contrasena(contraseña)

        cur.execute("""
            INSERT INTO usuarios (nombre, apellido_paterno, apellido_materno, usuario, contraseña, rol, es_maestro)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            nombre,
            apellido_paterno,
            apellido_materno,
            usuario,
            contraseña_encriptada,
            rol,
            es_maestro
        ))

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
@login_requerido
def vista_agregar_personal():
    return render_template("agregar_personal.html")


# Actualizar personal
@app.route("/api/actualizar_personal/<clave>", methods=["PUT"])
def actualizar_personal(clave):
    data = request.get_json()
    conn = conectar_bd()
    cur = conn.cursor()

    try:
        nombre = data.get("nombre")
        apellido_paterno = data.get("apellido_paterno")
        apellido_materno = data.get("apellido_materno")
        puesto = data.get("puesto")

        if not all([nombre, apellido_paterno, apellido_materno, puesto]):
            return jsonify({
                "success": False,
                "message": "Faltan datos para actualizar"
            }), 400

        cur.execute("""
            UPDATE personal
            SET nombre = %s,
                apellido_paterno = %s,
                apellido_materno = %s,
                puesto = %s
            WHERE clave = %s
        """, (nombre, apellido_paterno, apellido_materno, puesto, clave))

        conn.commit()

        if cur.rowcount > 0:
            return jsonify({
                "success": True,
                "message": "Personal actualizado correctamente"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "No se encontró el registro"
            }), 404

    except Exception as e:
        conn.rollback()
        print("Error al actualizar personal:", e)
        return jsonify({
            "success": False,
            "message": "Error al actualizar personal"
        }), 500

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
@login_requerido
def vista_docentes():
    return render_template("docentes.html")

@app.route("/estudiantes")
@login_requerido
def vista_estudiantes():
    return render_template("estudiantes.html")

@app.route("/reporte-docentes-asistencias")
@login_requerido
def vista_reporte_docentes_asistencias():
    return render_template("Generar_Reporte_Docentes_Asistencias.html")


@app.route("/reporte-docentes-general")
@login_requerido
def vista_reporte_docentes_general():
    return render_template("Generar_reporte_docentes_general.html")

@app.route("/reporte-docentes-inasistencias")
@login_requerido
def vista_reporte_docentes_inasistencias():
    return render_template("Generar_Reporte_Docentes_Inasistencias.html")

@app.route("/reporte-docentes-justificaciones")
@login_requerido
def vista_reporte_docentes_justificaciones():
    return render_template("Generar_Reporte_Docentes_Justificaciones.html")

@app.route("/reporte-estudiantes-asistencias")
@login_requerido
def vista_reporte_estudiantes_asistencias():
    return render_template("Generar_Reporte_Estudiantes_Asistencias.html")

@app.route("/reporte-estudiantes-general")
@login_requerido
def vista_reporte_estudiantes_general():
    return render_template("Generar_Reporte_Estudiantes_General.html")

@app.route("/reporte-estudiantes-inasistencias")
@login_requerido
def vista_reporte_estudiantes_inasistencias():
    return render_template("Generar_Reporte_Estudiantes_Inasistencias.html")

@app.route("/reporte-estudiantes-justificaciones")
@login_requerido
def vista_reporte_estudiantes_justificaciones():
    return render_template("Generar_Reporte_Estudiantes_Justificaciones.html")

@app.route("/historial")
@login_requerido
def vista_historial():
    return render_template("historial.html")

@app.route("/informacion-docente")
@login_requerido
def vista_informacion_docente():
    return render_template("informacion_docente.html")

@app.route("/informacion-estudiante")
@login_requerido
def vista_informacion_estudiante():
    return render_template("informacion_estudiante.html")

@app.route("/")
def vista_login():
    return render_template("login.html")

@app.route("/login")
def login_vista():
    return render_template("login.html")

@app.route("/modificar-reporte-docentes")
@login_requerido
def vista_modificar_reporte_docentes():
    return render_template("Modificar_Reporte_Docentes.html")

@app.route("/modificar-reporte-estudiantes")
@login_requerido
def vista_modificar_reporte_estudiantes():
    return render_template("Modificar_Reporte_Estudiantes.html")

@app.route("/panel-inicio")
@login_requerido
def vista_panel_inicio():
    return render_template("panel_inicio.html")

@app.route("/administrar-usuarios")
@login_requerido
def administrar_usuarios():
    if not session.get("es_maestro"):
        return redirect("/panel-inicio")

    return render_template("administrar_usuarios.html")

@app.route("/api/listar_usuarios", methods=["GET"])
@login_requerido
def listar_usuarios():
    if not session.get("es_maestro"):
        return jsonify({
            "success": False,
            "message": "Acceso no autorizado"
        }), 403

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, nombre, apellido_paterno, apellido_materno, usuario, rol, es_maestro
            FROM usuarios
            ORDER BY id ASC
        """)
        resultados = cur.fetchall()

        usuarios = []
        for u in resultados:
            usuarios.append({
                "id": u[0],
                "nombre": u[1],
                "apellido_paterno": u[2],
                "apellido_materno": u[3],
                "usuario": u[4],
                "rol": u[5],
                "es_maestro": u[6]
            })

        return jsonify({
            "success": True,
            "usuarios": usuarios
        }), 200

    except Exception as e:
        print("Error al listar usuarios:", e)
        return jsonify({
            "success": False,
            "message": "Error al listar usuarios"
        }), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/eliminar_usuario/<int:id_usuario>", methods=["DELETE"])
@login_requerido
def eliminar_usuario(id_usuario):
    if not session.get("es_maestro"):
        return jsonify({
            "success": False,
            "message": "Acceso no autorizado"
        }), 403

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        # Buscar el usuario que intenta borrar
        cur.execute("""
            SELECT id, usuario, es_maestro
            FROM usuarios
            WHERE id = %s
        """, (id_usuario,))
        usuario_objetivo = cur.fetchone()

        if not usuario_objetivo:
            return jsonify({
                "success": False,
                "message": "Usuario no encontrado"
            }), 404

        # Evitar borrar cuentas master
        if usuario_objetivo[2] == True:
            return jsonify({
                "success": False,
                "message": "No se puede eliminar una cuenta maestra"
            }), 403

        # Evitar que el master se borre a sí mismo, por seguridad extra
        if usuario_objetivo[1] == session.get("usuario"):
            return jsonify({
                "success": False,
                "message": "No puedes eliminar tu propia cuenta"
            }), 403

        cur.execute("""
            DELETE FROM usuarios
            WHERE id = %s
        """, (id_usuario,))

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Usuario eliminado correctamente"
        }), 200

    except Exception as e:
        conn.rollback()
        print("Error al eliminar usuario:", e)
        return jsonify({
            "success": False,
            "message": "Error al eliminar usuario"
        }), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/dashboard", methods=["GET"])
@login_requerido
def dashboard():
    conn = conectar_bd()
    cur = conn.cursor()

    try:
        # Total alumnos
        cur.execute("SELECT COUNT(*) FROM estudiantes")
        total_alumnos = cur.fetchone()[0]

        # Total personal
        cur.execute("SELECT COUNT(*) FROM personal")
        total_personal = cur.fetchone()[0]

        # =========================
        # ALUMNOS HOY
        # =========================

        # Asistencias alumnos
        cur.execute("""
            SELECT COUNT(*)
            FROM asistencias
            WHERE fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
              AND estado_asistencia = 'Asistencia'
        """)
        asistencias_alumnos_hoy = cur.fetchone()[0]

        # Inasistencias alumnos
        cur.execute("""
            SELECT COUNT(*)
            FROM asistencias
            WHERE fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
              AND estado_asistencia = 'Inasistencia'
        """)
        inasistencias_alumnos_hoy = cur.fetchone()[0]

        # Justificaciones alumnos
        cur.execute("""
            SELECT COUNT(*)
            FROM asistencias
            WHERE fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
              AND estado_asistencia = 'Justificación'
        """)
        justificaciones_alumnos_hoy = cur.fetchone()[0]

        # =========================
        # PERSONAL HOY
        # =========================

        # Asistencias personal
        cur.execute("""
            SELECT COUNT(*)
            FROM asistencias_personal
            WHERE fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
              AND estado_asistencia = 'Asistencia'
        """)
        asistencias_personal_hoy = cur.fetchone()[0]

        # Inasistencias personal
        cur.execute("""
            SELECT COUNT(*)
            FROM asistencias_personal
            WHERE fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
              AND estado_asistencia = 'Inasistencia'
        """)
        inasistencias_personal_hoy = cur.fetchone()[0]

        # Justificaciones personal
        cur.execute("""
            SELECT COUNT(*)
            FROM asistencias_personal
            WHERE fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
              AND estado_asistencia = 'Justificación'
        """)
        justificaciones_personal_hoy = cur.fetchone()[0]

        # =========================
        # TOTALES GENERALES
        # =========================

        asistencias_hoy = asistencias_alumnos_hoy + asistencias_personal_hoy
        inasistencias_hoy = inasistencias_alumnos_hoy + inasistencias_personal_hoy

        return jsonify({
            "success": True,
            "total_alumnos": total_alumnos,
            "total_personal": total_personal,
            "asistencias_hoy": asistencias_hoy,
            "inasistencias": inasistencias_hoy,

            # Gráfica alumnos
            "alumnos_asistencias": asistencias_alumnos_hoy,
            "alumnos_inasistencias": inasistencias_alumnos_hoy,
            "alumnos_justificaciones": justificaciones_alumnos_hoy,

            # Gráfica personal
            "personal_asistencias": asistencias_personal_hoy,
            "personal_inasistencias": inasistencias_personal_hoy,
            "personal_justificaciones": justificaciones_personal_hoy
        }), 200

    except Exception as e:
        print("Error dashboard:", e)
        return jsonify({
            "success": False,
            "message": "Error al cargar dashboard"
        }), 500

    finally:
        cur.close()
        conn.close()
        
@app.route("/registro")
@login_requerido
def vista_registro():
    return render_template("registro.html")

@app.route("/reporte-docentes")
@login_requerido
def vista_reporte_docentes():
    return render_template("reporte_docentes.html")

@app.route("/reporte-estudiantes")
@login_requerido
def vista_reporte_estudiantes():
    return render_template("reporte_estudiantes.html")

@app.route("/reportes-grupales-estudiantes-asistencias")
@login_requerido
def vista_rg_estudiantes_asistencias():
    return render_template("Reportes_Grupales_Estudiantes_Asistencias.html")

@app.route("/reportes-grupales-estudiantes-general")
@login_requerido
def vista_rg_estudiantes_general():
    return render_template("Reportes_Grupales_Estudiantes_General.html")

@app.route("/reportes-grupales-estudiantes-inasistencias")
@login_requerido
def vista_rg_estudiantes_inasistencias():
    return render_template("Reportes_Grupales_Estudiantes_Inasistencias.html")

@app.route("/reportes-grupales-estudiantes-justificaciones")
@login_requerido
def vista_rg_estudiantes_justificaciones():
    return render_template("Reportes_Grupales_Estudiantes_Justificaciones.html")

@app.route("/reportes-grupales-docentes-asistencias")
@login_requerido
def vista_rg_docentes_asistencias():
    return render_template("Reportes_Grupales_Docentes_Asistencias.html")

@app.route("/reportes-grupales-docentes-general")
@login_requerido
def vista_rg_docentes_general():
    return render_template("Reportes_Grupales_Docentes_General.html")

@app.route("/reportes-grupales-docentes-inasistencias")
@login_requerido
def vista_rg_docentes_inasistencias():
    return render_template("Reportes_Grupales_Docentes_Inasistencias.html")

@app.route("/reportes-grupales-docentes-justificaciones")
@login_requerido
def vista_rg_docentes_justificaciones():
    return render_template("Reportes_Grupales_Docentes_Justificaciones.html")

@app.route("/reportes-grupales-administrativo-asistencias")
@login_requerido
def vista_rg_admin_asistencias():
    return render_template("Reportes_Grupales_Administrativo_Asistencias.html")

@app.route("/reportes-grupales-administrativo-general")
@login_requerido
def vista_rg_admin_general():
    return render_template("Reportes_Grupales_Administrativo_General.html")

@app.route("/reportes-grupales-administrativo-inasistencias")
@login_requerido
def vista_rg_admin_inasistencias():
    return render_template("Reportes_Grupales_Administrativo_Inasistencias.html")

@app.route("/reportes-grupales-administrativo-justificaciones")
@login_requerido
def vista_rg_admin_justificaciones():
    return render_template("Reportes_Grupales_Administrativo_Justificaciones.html")

@app.route("/reportes")
@login_requerido
def vista_reportes():
    return render_template("reportes.html")

@app.route("/cambiar-contrasena")
@login_requerido
def vista_cambiar_contrasena():
    return render_template("cambiar_contrasena.html")

@app.route("/restablecer-contrasena")
@login_requerido
def vista_restablecer_contrasena():
    return render_template("restablecer_contrasena.html")

@app.route("/api/restablecer-contrasena", methods=["POST"])
@login_requerido
def restablecer_contrasena():
    data = request.get_json() or {}

    usuario_master = data.get("usuario_master")
    password_master = data.get("password_master")
    usuario_objetivo = data.get("usuario_objetivo")
    nueva_password = data.get("nueva_password")

    if not usuario_master or not password_master or not usuario_objetivo or not nueva_password:
        return jsonify({"success": False, "message": "Faltan datos"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT es_maestro, contraseña
            FROM usuarios
            WHERE usuario = %s
        """, (usuario_master,))

        resultado = cur.fetchone()

        if not resultado:
            return jsonify({
                "success": False,
                "message": "Credenciales de master incorrectas"
            }), 401

        es_maestro = resultado[0]
        hash_master = resultado[1]

        if not es_maestro or not verificar_contrasena(password_master, hash_master):
            return jsonify({
                "success": False,
                "message": "Credenciales de master incorrectas"
            }), 401

        cur.execute("""
            SELECT id FROM usuarios WHERE usuario = %s
        """, (usuario_objetivo,))

        existe = cur.fetchone()

        if not existe:
            return jsonify({
                "success": False,
                "message": "El usuario a restablecer no existe"
            }), 404

        nueva_hash = encriptar_contrasena(nueva_password)

        cur.execute("""
            UPDATE usuarios
            SET contraseña = %s
            WHERE usuario = %s
        """, (nueva_hash, usuario_objetivo))

        conn.commit()

        return jsonify({
            "success": True,
            "message": f"Contraseña restablecida para {usuario_objetivo}"
        }), 200

    except Exception as e:
        conn.rollback()
        print("Error al restablecer contraseña:", e)
        return jsonify({
            "success": False,
            "message": "Error en el servidor"
        }), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/cambiar-contrasena", methods=["POST"])
@login_requerido
def cambiar_contrasena():
    data = request.get_json() or {}

    usuario = data.get("usuario")
    actual = data.get("actual")
    nueva = data.get("nueva")

    if not usuario or not actual or not nueva:
        return jsonify({"success": False, "message": "Faltan datos"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT contraseña
            FROM usuarios
            WHERE usuario = %s
        """, (usuario,))

        resultado = cur.fetchone()

        if not resultado:
            return jsonify({"success": False, "message": "❌ Usuario no encontrado. debe darse de alta primero"}), 404

        hash_guardado = resultado[0]

        if not verificar_contrasena(actual, hash_guardado):
            return jsonify({
                "success": False,
                "message": "Usuario o contraseña actual incorrectos"
            }), 401

        nueva_hash = encriptar_contrasena(nueva)

        cur.execute("""
            UPDATE usuarios
            SET contraseña = %s
            WHERE usuario = %s
        """, (nueva_hash, usuario))

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Contraseña actualizada correctamente"
        }), 200

    except Exception as e:
        conn.rollback()
        print("Error al cambiar contraseña:", e)
        return jsonify({
            "success": False,
            "message": "Error en el servidor"
        }), 500

    finally:
        cur.close()
        conn.close()


@app.route("/api/validar-admin-master", methods=["POST"])
@login_requerido
def validar_admin_master():
    data = request.get_json() or {}
    usuario = data.get("usuario")
    contraseña = data.get("contraseña")

    if not usuario or not contraseña:
        return jsonify({"success": False, "message": "Faltan credenciales"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT rol, es_maestro, contraseña
            FROM usuarios
            WHERE usuario = %s
        """, (usuario,))
        resultado = cur.fetchone()

        if not resultado:
            return jsonify({"success": False, "message": "Credenciales incorrectas"}), 401

        rol = resultado[0]
        es_maestro = resultado[1]
        hash_guardado = resultado[2]

        if (rol == "admin" or es_maestro) and verificar_contrasena(contraseña, hash_guardado):
            return jsonify({"success": True, "message": "Acceso autorizado"}), 200
        else:
            return jsonify({"success": False, "message": "Credenciales incorrectas o sin permisos"}), 401

    except Exception as e:
        print("Error al validar admin/master:", e)
        return jsonify({"success": False, "message": "Error en el servidor"}), 500

    finally:
        cur.close()
        conn.close()

@app.route("/api/modificar-reporte-personal", methods=["GET"])
@login_requerido
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
            SELECT 
                ap.id,
                p.clave,
                p.nombre,
                p.apellido_paterno,
                p.apellido_materno,
                p.puesto,
                ap.fecha_dia,
                ap.estado_asistencia,
                ap.motivo_justificacion
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
                "id": r[0],
                "clave": r[1],
                "nombre": r[2],
                "apellido_paterno": r[3],
                "apellido_materno": r[4],
                "puesto": r[5],
                "fecha": r[6].strftime("%Y-%m-%d") if r[6] else "",
                "estado_asistencia": r[7],
                "motivo_justificacion": r[8]
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
                       a.fecha, a.estado_asistencia, a.motivo_justificacion
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
                "estado_asistencia": r[6],
                "motivo_justificacion": r[7]
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
    data = request.get_json() or {}
    cambios = data.get("cambios", [])

    if not cambios:
        return jsonify({"success": False, "message": "No se recibieron cambios"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        total_actualizados = 0

        for cambio in cambios:
            asistencia_id = cambio.get("id")
            estado = cambio.get("estado_asistencia")
            motivo = cambio.get("motivo_justificacion")

            if not asistencia_id or not estado:
                return jsonify({
                    "success": False,
                    "message": "Datos incompletos en un cambio"
                }), 400

            if estado != "Justificación":
                motivo = None

            cur.execute("""
                UPDATE asistencias_personal
                SET estado_asistencia = %s,
                    motivo_justificacion = %s
                WHERE id = %s
            """, (estado, motivo, asistencia_id))

            total_actualizados += cur.rowcount

        conn.commit()

        if total_actualizados == 0:
            return jsonify({
                "success": False,
                "message": "No se encontró ningún registro para actualizar."
            }), 404

        return jsonify({
            "success": True,
            "message": "Cambios guardados correctamente"
        }), 200

    except Exception as e:
        conn.rollback()
        print("Error al guardar cambios del personal:", e)
        return jsonify({
            "success": False,
            "message": f"Error al guardar cambios: {str(e)}"
        }), 500

    finally:
        cur.close()
        conn.close()

# Eliminar registro de asistencia del personal
@app.route("/api/eliminar-registro-personal", methods=["POST"])
def eliminar_registro_personal():
    data = request.get_json() or {}
    asistencia_id = data.get("id")

    if not asistencia_id:
        return jsonify({
            "success": False,
            "message": "Falta el ID del registro"
        }), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM asistencias_personal
            WHERE id = %s
        """, (asistencia_id,))

        filas_afectadas = cur.rowcount
        conn.commit()

        if filas_afectadas > 0:
            return jsonify({
                "success": True,
                "message": "Registro eliminado correctamente"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "No se encontró el registro"
            }), 404

    except Exception as e:
        conn.rollback()
        print("Error al eliminar registro personal:", e)
        return jsonify({
            "success": False,
            "message": "Error al eliminar registro"
        }), 500

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


@app.route("/api/guardar-cambios", methods=["POST"])
def guardar_cambios():
    data = request.get_json() or {}
    cambios = data.get("cambios", [])

    if not cambios:
        return jsonify({"success": False, "message": "No se recibieron cambios"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        total_actualizados = 0

        for cambio in cambios:
            asistencia_id = cambio.get("id")
            estado = cambio.get("estado_asistencia")
            motivo = cambio.get("motivo_justificacion")

            if not asistencia_id or not estado:
                return jsonify({
                    "success": False,
                    "message": "Datos incompletos en un cambio"
                }), 400

            if estado != "Justificación":
                motivo = None

            cur.execute("""
                UPDATE asistencias
                SET estado_asistencia = %s,
                    motivo_justificacion = %s
                WHERE id = %s
            """, (estado, motivo, asistencia_id))

            total_actualizados += cur.rowcount

        conn.commit()

        if total_actualizados == 0:
            return jsonify({
                "success": False,
                "message": "No se encontró ningún registro para actualizar."
            }), 404

        return jsonify({
            "success": True,
            "message": "Cambios guardados correctamente"
        }), 200

    except Exception as e:
        conn.rollback()
        print("Error al guardar cambios:", e)
        return jsonify({
            "success": False,
            "message": f"Error al guardar cambios: {str(e)}"
        }), 500

    finally:
        cur.close()
        conn.close()

# Listar asistencias con filtros avanzados
@app.route("/api/listar-asistencias", methods=["POST"])
def listar_asistencias():
    data = request.get_json() or {}
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")
    comunidad = data.get("comunidad")
    tipo_reporte = data.get("tipo_reporte")

    carrera = data.get("carrera")
    semestre = data.get("semestre")
    grupo = data.get("grupo")

    if not fecha_inicio or not fecha_fin or not comunidad or not tipo_reporte:
        return jsonify({"success": False, "message": "Faltan parámetros obligatorios"}), 400

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        if comunidad == "estudiantes":
            query = """
                SELECT e.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                       e.carrera, e.semestre, e.grupo,
                       to_char(a.fecha AT TIME ZONE 'America/Mexico_City', 'DD/MM/YYYY HH12:MI AM') AS fecha,
                       a.estado_asistencia,
                       a.motivo_justificacion
                FROM asistencias a
                JOIN estudiantes e ON a.matricula = e.matricula
                WHERE a.fecha >= %s
                  AND a.fecha < %s::date + INTERVAL '1 day'
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
                       a.estado_asistencia,
                       a.motivo_justificacion
                FROM asistencias_personal a
                JOIN personal p ON a.personal_id = p.id
                WHERE a.fecha >= %s
                  AND a.fecha < %s::date + INTERVAL '1 day'
            """
            params = [fecha_inicio, fecha_fin]

            if comunidad == "docentes":
                query += """
                    AND LOWER(TRIM(p.puesto)) LIKE %s
                """
                params.append("%docente%")

            elif comunidad == "administrativo":
                query += """
                    AND (
                        LOWER(TRIM(p.puesto)) LIKE %s
                        OR LOWER(TRIM(p.puesto)) LIKE %s
                        OR LOWER(TRIM(p.puesto)) LIKE %s
                        OR LOWER(TRIM(p.puesto)) LIKE %s
                    )
                """
                params.extend([
                    "%administrativo%",
                    "%coordinador%",
                    "%dirección%",
                    "%direccion%"
                ])

        else:
            return jsonify({"success": False, "message": "Comunidad no válida"}), 400

        if tipo_reporte == "asistencias":
            query += " AND a.estado_asistencia = 'Asistencia'"
        elif tipo_reporte == "inasistencias":
            query += " AND a.estado_asistencia = 'Inasistencia'"
        elif tipo_reporte == "justificaciones":
            query += " AND a.estado_asistencia = 'Justificación'"
        elif tipo_reporte == "general":
            pass
        else:
            return jsonify({"success": False, "message": "Tipo de reporte no válido"}), 400

        query += " ORDER BY a.fecha DESC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        resultados = []
        for r in rows:
            registro = {
                "fecha": r[-3],
                "estado_asistencia": r[-2],
                "motivo_justificacion": r[-1]
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


@app.route("/api/registrar-asistencia", methods=["POST"])
def registrar_asistencia():
    data = request.get_json() or {}
    codigo = data.get("codigo_qr")

    if not codigo:
        return jsonify({
            "success": False,
            "message": "❌ No se recibió código QR valido"
        }), 400

    codigo = str(codigo).strip()

    conn = conectar_bd()
    cur = conn.cursor()

    try:
        # =========================
        # BUSCAR ESTUDIANTE
        # =========================
        cur.execute("""
            SELECT matricula, nombre, chat_id_telegram
            FROM estudiantes
            WHERE matricula::text = %s
        """, (codigo,))
        alumno = cur.fetchone()

        if alumno:
            matricula, nombre, chat_id_tutor = alumno

            cur.execute("""
                SELECT id, estado_asistencia, hora_entrada, hora_salida
                FROM asistencias
                WHERE matricula = %s
                  AND fecha_dia = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Mexico_City')::date
            """, (matricula,))
            registro = cur.fetchone()

            def destinatarios_estudiante():
                destinos = [CHAT_ID_ADMIN]
                if chat_id_tutor and str(chat_id_tutor).strip():
                    destinos.append(str(chat_id_tutor).strip())
                return destinos

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

                fecha_local = datetime.now().strftime("%d/%m/%Y")
                hora_local = datetime.now().strftime("%I:%M %p")

                mensaje = (
                    f"✅ Entrada registrada\n"
                    f"Nombre: {nombre}\n"
                    f"Matrícula: {matricula}\n"
                    f"Tipo: Estudiante\n"
                    f"Fecha: {fecha_local}\n"
                    f"Hora: {hora_local}"
                )
                enviar_telegram_multiple(mensaje, destinatarios_estudiante())

                return jsonify({
                    "success": True,
                    "tipo_registro": "entrada",
                    "message": f"Entrada registrada: {nombre}",
                    "nombre": nombre,
                    "matricula": matricula,
                    "estado": "Asistencia"
                }), 200

            asistencia_id, estado_actual, hora_entrada, hora_salida = registro

            if hora_entrada is None:
                cur.execute("""
                    UPDATE asistencias
                    SET hora_entrada = CURRENT_TIMESTAMP,
                        estado_asistencia = 'Asistencia',
                        fecha = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (asistencia_id,))
                conn.commit()

                fecha_local = datetime.now().strftime("%d/%m/%Y")
                hora_local = datetime.now().strftime("%I:%M %p")

                mensaje = (
                    f"✅ Entrada registrada\n"
                    f"Nombre: {nombre}\n"
                    f"Matrícula: {matricula}\n"
                    f"Tipo: Estudiante\n"
                    f"Fecha: {fecha_local}\n"
                    f"Hora: {hora_local}"
                )
                enviar_telegram_multiple(mensaje, destinatarios_estudiante())

                return jsonify({
                    "success": True,
                    "tipo_registro": "entrada",
                    "message": f"Entrada registrada: {nombre}",
                    "nombre": nombre,
                    "matricula": matricula,
                    "estado": "Asistencia"
                }), 200

            if hora_salida is None:
                cur.execute("""
                    UPDATE asistencias
                    SET hora_salida = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (asistencia_id,))
                conn.commit()

                fecha_local = datetime.now().strftime("%d/%m/%Y")
                hora_local = datetime.now().strftime("%I:%M %p")

                mensaje = (
                    f"🚪 Salida registrada\n"
                    f"Nombre: {nombre}\n"
                    f"Matrícula: {matricula}\n"
                    f"Tipo: Estudiante\n"
                    f"Fecha: {fecha_local}\n"
                    f"Hora: {hora_local}"
                )
                enviar_telegram_multiple(mensaje, destinatarios_estudiante())

                return jsonify({
                    "success": True,
                    "tipo_registro": "salida",
                    "message": f"Salida registrada: {nombre}",
                    "nombre": nombre,
                    "matricula": matricula,
                    "estado": estado_actual
                }), 200

            return jsonify({
                "success": False,
                "message": f"Entrada y salida ya registradas hoy para {nombre}",
                "nombre": nombre,
                "matricula": matricula,
                "estado": estado_actual
            }), 200

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

                fecha_local = datetime.now().strftime("%d/%m/%Y")
                hora_local = datetime.now().strftime("%I:%M %p")

                mensaje = (
                    f"✅ Entrada registrada\n"
                    f"Nombre: {nombre}\n"
                    f"Clave: {clave}\n"
                    f"Tipo: Personal\n"
                    f"Fecha: {fecha_local}\n"
                    f"Hora: {hora_local}"
                )
                enviar_telegram_multiple(mensaje, [CHAT_ID_ADMIN])

                return jsonify({
                    "success": True,
                    "tipo_registro": "entrada",
                    "message": f"Entrada registrada: {nombre}",
                    "nombre": nombre,
                    "clave": clave,
                    "estado": "Asistencia"
                }), 200

            asistencia_id, estado_actual, hora_entrada, hora_salida = registro

            if hora_entrada is None:
                cur.execute("""
                    UPDATE asistencias_personal
                    SET hora_entrada = CURRENT_TIMESTAMP,
                        estado_asistencia = 'Asistencia',
                        fecha = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (asistencia_id,))
                conn.commit()

                fecha_local = datetime.now().strftime("%d/%m/%Y")
                hora_local = datetime.now().strftime("%I:%M %p")

                mensaje = (
                    f"✅ Entrada registrada\n"
                    f"Nombre: {nombre}\n"
                    f"Clave: {clave}\n"
                    f"Tipo: Personal\n"
                    f"Fecha: {fecha_local}\n"
                    f"Hora: {hora_local}"
                )
                enviar_telegram_multiple(mensaje, [CHAT_ID_ADMIN])

                return jsonify({
                    "success": True,
                    "tipo_registro": "entrada",
                    "message": f"Entrada registrada: {nombre}",
                    "nombre": nombre,
                    "clave": clave,
                    "estado": "Asistencia"
                }), 200

            if hora_salida is None:
                cur.execute("""
                    UPDATE asistencias_personal
                    SET hora_salida = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (asistencia_id,))
                conn.commit()

                fecha_local = datetime.now().strftime("%d/%m/%Y")
                hora_local = datetime.now().strftime("%I:%M %p")

                mensaje = (
                    f"🚪 Salida registrada\n"
                    f"Nombre: {nombre}\n"
                    f"Clave: {clave}\n"
                    f"Tipo: Personal\n"
                    f"Fecha: {fecha_local}\n"
                    f"Hora: {hora_local}"
                )
                enviar_telegram_multiple(mensaje, [CHAT_ID_ADMIN])

                return jsonify({
                    "success": True,
                    "tipo_registro": "salida",
                    "message": f"Salida registrada: {nombre}",
                    "nombre": nombre,
                    "clave": clave,
                    "estado": estado_actual
                }), 200

            return jsonify({
                "success": False,
                "message": f"Entrada y salida ya registradas hoy para {nombre}",
                "nombre": nombre,
                "clave": clave,
                "estado": estado_actual
            }), 200

        return jsonify({
            "success": False,
            "message": "❌ Usuario no encontrado. debe darse de alta primero"
        }), 404

    except Exception as e:
        conn.rollback()
        print("Error al registrar asistencia:", e)
        return jsonify({
            "success": False,
            "message": "❌ Error al registrar asistencia"
        }), 500

    finally:
        cur.close()
        conn.close()

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
    from flask import request, send_file
    from qrcode.constants import ERROR_CORRECT_L

    # 🔥 SOLO el código, NO URL
    contenido = str(codigo).strip()

    qr = qrcode.QRCode(
        version=1,  # QR pequeño
        error_correction=ERROR_CORRECT_L,  # más rápido de leer
        box_size=7,  # tamaño moderado (puedes probar 6-8)
        border=3
    )

    qr.add_data(contenido)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    # Descargar
    if request.args.get("download") == "1":
        return send_file(
            buf,
            mimetype="image/png",
            as_attachment=True,
            download_name=f"qr_{codigo}.png"
        )
    else:
        return send_file(buf, mimetype="image/png")
@app.route("/api/cargar-estudiantes-excel", methods=["POST"])
def cargar_estudiantes_excel():
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No se envió archivo"}), 400

    file = request.files["file"]

    try:
        df = pd.read_excel(file, header=3)

        # Normalizar nombres de columnas
        df.columns = [str(col).strip().lower() for col in df.columns]

        columnas_requeridas = [
            "matricula", "nombre", "apellido_paterno",
            "apellido_materno", "carrera", "semestre", "grupo"
        ]

        for col in columnas_requeridas:
            if col not in df.columns:
                return jsonify({"success": False, "message": f"Falta columna: {col}"}), 400

        if "chat_id_telegram" not in df.columns:
            df["chat_id_telegram"] = None

        conn = conectar_bd()
        cur = conn.cursor()

        insertados = 0
        actualizados = 0
        errores = []
        matriculas_excel = set()

        for _, row in df.iterrows():
            try:
                matricula = str(row["matricula"]).strip()
                nombre = str(row["nombre"]).strip() if pd.notna(row["nombre"]) else None
                apellido_paterno = str(row["apellido_paterno"]).strip() if pd.notna(row["apellido_paterno"]) else None
                apellido_materno = str(row["apellido_materno"]).strip() if pd.notna(row["apellido_materno"]) else None
                carrera = str(row["carrera"]).strip() if pd.notna(row["carrera"]) else None
                semestre = str(row["semestre"]).strip() if pd.notna(row["semestre"]) else None
                grupo = str(row["grupo"]).strip() if pd.notna(row["grupo"]) else None

                chat_id_telegram = row["chat_id_telegram"]
                if pd.isna(chat_id_telegram) or str(chat_id_telegram).strip() == "":
                    chat_id_telegram = None
                else:
                    chat_id_telegram = str(chat_id_telegram).strip()
                    if not chat_id_telegram.isdigit():
                        raise ValueError("El chat_id_telegram solo debe contener números")

                # Validar repetidos dentro del mismo Excel
                if matricula in matriculas_excel:
                    raise ValueError("Matrícula repetida dentro del archivo Excel")

                matriculas_excel.add(matricula)

                # Verificar si ya existe en BD
                cur.execute("SELECT 1 FROM estudiantes WHERE matricula = %s", (matricula,))
                existe = cur.fetchone()

                if existe:
                    cur.execute("""
                        UPDATE estudiantes
                        SET nombre = %s,
                            apellido_paterno = %s,
                            apellido_materno = %s,
                            carrera = %s,
                            semestre = %s,
                            grupo = %s,
                            chat_id_telegram = %s
                        WHERE matricula = %s
                    """, (
                        nombre,
                        apellido_paterno,
                        apellido_materno,
                        carrera,
                        semestre,
                        grupo,
                        chat_id_telegram,
                        matricula
                    ))
                    actualizados += 1
                else:
                    cur.execute("""
                        INSERT INTO estudiantes (
                            matricula, nombre, apellido_paterno, apellido_materno,
                            carrera, semestre, grupo, chat_id_telegram
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        matricula,
                        nombre,
                        apellido_paterno,
                        apellido_materno,
                        carrera,
                        semestre,
                        grupo,
                        chat_id_telegram
                    ))
                    insertados += 1

            except Exception as e:
                errores.append({
                    "matricula": row["matricula"] if "matricula" in row else "Sin matrícula",
                    "error": str(e)
                })

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "insertados": insertados,
            "actualizados": actualizados,
            "errores": errores,
            "total": len(df)
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": f"Error procesando archivo: {str(e)}"}), 500
@app.route("/verificacion")
def vista_verificacion():
    return render_template("verificación.html")

@app.route("/verificacion-usuarios")
def vista_verificacion_usuarios():
    if not session.get("verificacion_autorizada"):
        return redirect(url_for("acceso_verificacion"))
    return render_template("Verificacion_Usuarios.html")

@app.route("/cerrar-verificacion")
def cerrar_verificacion():
    session.pop("verificacion_autorizada", None)
    session.pop("usuario_verificacion", None)
    return redirect(url_for("acceso_verificacion"))

# 🚀 Ejecutar la app
import os

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    # Iniciar el ciclo de sincronización de Telegram en un hilo separado
       threading.Thread(target=ciclo_telegram, daemon=True).start()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        ssl_context=("cert.pem", "key.pem")
    )

