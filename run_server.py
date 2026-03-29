import os
import sys
import threading
import webbrowser
from app import app

def ruta_ejecutable(nombre_archivo):
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, nombre_archivo)

def abrir_navegador():
    webbrowser.open("https://127.0.0.1:5000/login")

if __name__ == "__main__":
    cert_path = ruta_ejecutable("cert.pem")
    key_path = ruta_ejecutable("key.pem")

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        raise FileNotFoundError("No se encontraron cert.pem y key.pem junto al ejecutable.")

    threading.Timer(1.5, abrir_navegador).start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        ssl_context=(cert_path, key_path)
    )