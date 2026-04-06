from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Server is running and alive!"

def run():
    # Menjalankan server pada host 0.0.0.0 agar bisa diakses dari luar
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    """Memulai web server di background thread."""
    t = Thread(target=run)
    t.start()
