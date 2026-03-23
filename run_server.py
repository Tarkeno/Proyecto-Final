import threading
import webbrowser
from waitress import serve
from app import app  # cambia "app" si tu archivo principal tiene otro nombre

def abrir_navegador():
    webbrowser.open("http://127.0.0.1:8080/login")

if __name__ == "__main__":
    threading.Timer(1.5, abrir_navegador).start()
    serve(app, host="0.0.0.0", port=8080)