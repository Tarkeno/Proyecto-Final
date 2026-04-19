import os
import sys
import socket
import threading
import webbrowser
from app import app, ciclo_telegram


def ruta_ejecutable(nombre_archivo):
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, nombre_archivo)


def obtener_ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No necesita conexión real, solo ayuda a detectar la IP activa
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def abrir_navegador():
    ip_local = obtener_ip_local()
    webbrowser.open(f"https://{ip_local}:5000/login")


if __name__ == "__main__":
    cert_path = ruta_ejecutable("cert.pem")
    key_path = ruta_ejecutable("key.pem")

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        raise FileNotFoundError("No se encontraron cert.pem y key.pem junto al ejecutable.")

    # Iniciar sincronización automática de Telegram
    threading.Thread(target=ciclo_telegram, daemon=True).start()

    # Abrir navegador con la IP local real
    threading.Timer(1.5, abrir_navegador).start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        ssl_context=(cert_path, key_path)
    )