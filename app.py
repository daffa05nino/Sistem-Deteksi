from flask import Flask, render_template, request, redirect, url_for, session, flash, get_flashed_messages
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid
import io
import os
import base64
from functools import wraps
from PIL import Image
import logging

# -----------------------------
# CONFIG
# -----------------------------
DB_CONFIG = {
    'user': 'root',
    'password': '',
    'host': 'localhost',
    'database': 'sistemdeteksi'
}

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_CONTENT_LEN = 16 * 1024 * 1024  # 16 MB

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_sangat_kuat'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LEN

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

logging.basicConfig(level=logging.INFO)


# -----------------------------
# Helpers
# -----------------------------
def allowed_file_filename(filename):
    if not filename:
        return False
    return filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        app.logger.error(f"DB ERROR: {err}")
        return None


def save_local_file(file_obj, filename):
    safe = secure_filename(filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], safe)

    try:
        file_obj.seek(0)
        with open(path, 'wb') as f:
            f.write(file_obj.read())
        return f"uploads/{safe}"
    except Exception as e:
        app.logger.error(f"File save error: {e}")
        return None


def detect_image_type(file_obj):
    try:
        file_obj.seek(0)
        img = Image.open(file_obj)
        ext = img.format.lower()
        if ext == "jpeg":
            return "jpg"
        return ext
    except:
        return None


def render_template_with_messages(page, **ctx):
    msgs = get_flashed_messages(with_categories=True)
    ctx.setdefault("error", None)
    ctx.setdefault("success", None)

    for cat, msg in msgs:
        if cat == "error":
            ctx["error"] = msg
        elif cat == "success":
            ctx["success"] = msg
    return render_template(page, **ctx)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kw):
        if "user_id" not in session:
            flash("Anda harus login dulu!", "error")
            return redirect(url_for("login"))
        return f(*args, **kw)
    return wrapper


# Dummy model
def predict_defect(file_obj):
    if datetime.now().second % 2 == 0:
        return {"hasil": "CACAT", "score": 92.5}
    return {"hasil": "LOLOS", "score": 97.8}


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def index():
    return redirect(url_for("dashboard")) if "user_id" in session else redirect(url_for("login"))


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()
        if conn is None:
            return render_template_with_messages("login.html", error="DB Error")

        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM user WHERE username=%s", (username,))
        user = cur.fetchone()
        conn.close()

        if not user or not check_password_hash(user["password"], password):
            return render_template_with_messages("login.html", error="Username atau password salah")

        session["user_id"] = user["id_user"]
        session["full_name"] = user["nama"]

        flash("Login berhasil!", "success")
        return redirect(url_for("dashboard"))

    return render_template_with_messages("login.html")


# REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not nama or not username or not password:
            return render_template_with_messages("register.html", error="Semua kolom wajib diisi")

        if len(password) < 6:
            return render_template_with_messages("register.html", error="Password minimal 6 karakter")

        pw_hash = generate_password_hash(password)
        conn = get_db_connection()

        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO user (nama, username, password) VALUES (%s, %s, %s)",
                        (nama, username, pw_hash))
            conn.commit()
            return render_template_with_messages("login.html", success="Registrasi Berhasil!")
        except:
            return render_template_with_messages("register.html", error="Username sudah digunakan")
        finally:
            conn.close()

    return render_template_with_messages("register.html")


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    flash("Logout berhasil", "success")
    return redirect(url_for("login"))


# DASHBOARD
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()
    total = 0

    if conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM hasil_deteksi WHERE id_user=%s", (session["user_id"],))
        total = cur.fetchone()[0]
        conn.close()

    return render_template_with_messages("dashboard.html",
                                         full_name=session["full_name"],
                                         total_detections=total)


# HALAMAN DETEKSI
@app.route("/utama")
@login_required
def utama():
    ctx = {
        "full_name": session.get("full_name"),
        "detection_result": session.pop("detection_result", None),
        "detection_score": session.pop("detection_score", None),
        "raw_score": session.pop("raw_score", None),
        "image_path": session.pop("image_path", None),
        "timestamp": session.pop("timestamp", None),
        "timestamp_db": session.pop("timestamp_db", None),
    }
    return render_template_with_messages("utama.html", **ctx)


# PROSES DETEKSI
@app.route("/detect", methods=["POST"])
@login_required
def detect():
    file_obj = None
    filename = None

    # Upload biasa
    if "file" in request.files and request.files["file"].filename != "":
        f = request.files["file"]
        if not allowed_file_filename(f.filename):
            return render_template_with_messages("utama.html", error="Format tidak diizinkan")
        file_obj = io.BytesIO(f.read())
        filename = f.filename

    # Kamera
    elif request.form.get("camera_data"):
        raw = request.form["camera_data"]
        header, enc = raw.split(",", 1)
        data = base64.b64decode(enc)
        file_obj = io.BytesIO(data)
        ext = detect_image_type(file_obj) or "jpg"
        filename = f"capture_{uuid.uuid4().hex}.{ext}"

    else:
        return render_template_with_messages("utama.html", error="Tidak ada gambar")

    # Simpan file
    unique = f"{uuid.uuid4().hex}_{secure_filename(filename)}"
    rel_path = save_local_file(file_obj, unique)

    if not rel_path:
        return render_template_with_messages("utama.html", error="Gagal menyimpan file")

    # Prediksi
    file_obj.seek(0)
    pred = predict_defect(file_obj)
    score = float(pred["score"])

    session["detection_result"] = pred["hasil"]
    session["detection_score"] = f"{score:.2f}%"
    session["raw_score"] = score
    session["image_path"] = rel_path
    session["timestamp"] = datetime.now().strftime("%d %B %Y %H:%M:%S")
    session["timestamp_db"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return redirect(url_for("utama"))


# SIMPAN HASIL DETEKSI
@app.route("/save_detection", methods=["POST"])
@login_required
def save_detection():
    hasil = request.form.get("hasil")
    score = request.form.get("score")
    image = request.form.get("image_path")
    waktu = request.form.get("timestamp_db")

    score_val = float(score.replace("%", ""))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO hasil_deteksi (id_user, id_gambar, hasil, score, tanggal_deteksi)
        VALUES (%s, %s, %s, %s, %s)
    """, (session["user_id"], image, hasil, score_val, waktu))

    conn.commit()
    conn.close()

    flash("Data berhasil disimpan!", "success")
    return redirect(url_for("history"))


# RIWAYAT DETEKSI
@app.route('/history')
@login_required
def history():
    user_id = session.get('user_id')
    print("DEBUG user_id =", user_id)

    conn = get_db_connection()
    history_data = []

    if conn is None:
        return render_template_with_messages(
            'history.html',
            error="Kesalahan koneksi database.",
            history_data=[],
            full_name=session.get('full_name')
        )

    try:
        cursor = conn.cursor(dictionary=True)

        # Query tanpa DATE_FORMAT
        sql = """
            SELECT id_deteksi, id_gambar, hasil, score, tanggal_deteksi
            FROM hasil_deteksi
            WHERE id_user = %s
            ORDER BY tanggal_deteksi DESC
        """

        print("DEBUG SQL =", sql)
        cursor.execute(sql, (user_id,))
        rows = cursor.fetchall()

        # Format tanggal di Python (pasti berfungsi)
        for r in rows:
            try:
                r["formatted_date"] = r["tanggal_deteksi"].strftime("%d %b %Y, %H:%M:%S")
            except:
                r["formatted_date"] = "-"
            history_data.append(r)

    except mysql.connector.Error as e:
        app.logger.error(f"SQL error (history): {e}")
        return render_template_with_messages(
            'history.html',
            error="Gagal memuat riwayat.",
            history_data=[],
            full_name=session.get('full_name')
        )

    finally:
        conn.close()

    return render_template_with_messages(
        'history.html',
        history_data=history_data,
        full_name=session.get('full_name')
    )

# DELETE RIWAYAT
@app.route('/delete_detection/<int:id_deteksi>', methods=['POST'])
@login_required
def delete_detection(id_deteksi):
    user_id = session.get('user_id')

    conn = get_db_connection()
    if conn is None:
        flash("Kesalahan koneksi database.", "error")
        return redirect(url_for("history"))

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Ambil nama file gambar dari DB
        cursor.execute("""
            SELECT id_gambar FROM hasil_deteksi
            WHERE id_deteksi = %s AND id_user = %s
        """, (id_deteksi, user_id))
        data = cursor.fetchone()

        if not data:
            flash("Data tidak ditemukan.", "error")
            return redirect(url_for("history"))

        file_path = data["id_gambar"]  # contoh: uploads/abc123.png
        full_path = os.path.join(app.static_folder, file_path)

        # 2. Hapus data dari database
        cursor.execute("""
            DELETE FROM hasil_deteksi
            WHERE id_deteksi = %s AND id_user = %s
        """, (id_deteksi, user_id))
        conn.commit()

        # 3. Hapus file gambar fisik jika ada
        if os.path.exists(full_path):
            os.remove(full_path)
            print("FILE DELETED:", full_path)
        else:
            print("FILE NOT FOUND:", full_path)

        flash("Berhasil dihapus!", "success")

    except Exception as e:
        app.logger.error(f"Delete error: {e}")
        flash("Gagal menghapus data.", "error")

    finally:
        conn.close()

    return redirect(url_for('history'))




# MAIN
if __name__ == "__main__":
    app.run(debug=True)