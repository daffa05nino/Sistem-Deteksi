from flask import Flask, render_template, request, redirect, url_for, session, abort, flash, get_flashed_messages
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid
import io 
import os 
import base64 
from functools import wraps

# =========================================================================
# KONFIGURASI MYSQL - GANTI DENGAN SETTING ANDA
# =========================================================================
DB_CONFIG = {
    'user': 'root',
    'password': '', # <--- GANTI DI SINI (jika ada password)
    'host': 'localhost',
    'database': 'sistemdeteksi'
}
# =========================================================================

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_untuk_session_anda_yang_sangat_kuat_12345' 
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Batas ukuran file 16MB

# ----------------------------------------------------------------------
# FUNGSI UTILITAS
# ----------------------------------------------------------------------
def predict_defect(file_obj):
    """
    Fungsi DUMMY untuk prediksi.
    Ganti seluruh logic di fungsi ini dengan model AI (CNN) Anda.
    """
    # Mengembalikan dict dengan hasil dan skor mentah (Contoh: CACAT 92.7)
    # Menggunakan logika sederhana untuk bergantian hasil
    if datetime.now().second % 2 == 0:
        return {'hasil': 'CACAT', 'score': 92.7} 
    else:
        return {'hasil': 'LOLOS', 'score': 98.1}

def save_local_file(file_obj, filename):
    """Menyimpan file gambar ke folder static/uploads/ dan mengembalikan path relatif."""
    upload_dir = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    file_path = os.path.join(upload_dir, filename)
    
    file_obj.seek(0) 
    try:
        with open(file_path, 'wb') as f:
            f.write(file_obj.read())
        return os.path.join('uploads', filename).replace('\\', '/') 
    except Exception as e:
        print(f"Error saving file: {e}")
        return None
        
def get_db_connection():
    """Mencoba membuat dan mengembalikan koneksi database."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"FATAL: Database connection error: {err}")
        return None 

def login_required(f):
    """Dekorator untuk memastikan pengguna sudah login."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Anda perlu masuk untuk mengakses halaman ini.', 'error')
            return redirect(url_for('login')) 
        return f(*args, **kwargs)
    return wrapper

# ----------------------------------------------------------------------
# RUTE OTENTIKASI
# ----------------------------------------------------------------------

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard')) 
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        if conn is None:
            flash("Kesalahan koneksi database.", 'error')
            return render_template('login.html')

        cursor = conn.cursor(dictionary=True)
        sql = "SELECT id_user, nama, password FROM user WHERE username = %s"
        cursor.execute(sql, (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id_user']
            session['full_name'] = user['nama']
            return redirect(url_for('dashboard'))
        else:
            flash("Username atau Password salah.", 'error')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nama = request.form['nama']
        username = request.form['username']
        password = request.form['password']
        
        if not (nama and username and password):
            flash("Semua kolom harus diisi.", 'error')
            return render_template('register.html')
            
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        if conn is None:
            flash("Kesalahan koneksi database.", 'error')
            return render_template('register.html')
            
        cursor = conn.cursor()
        try:
            sql = "INSERT INTO user (nama, username, password) VALUES (%s, %s, %s)"
            cursor.execute(sql, (nama, username, hashed_password))
            conn.commit()
            flash("Registrasi berhasil! Silahkan masuk.", 'success')
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            conn.rollback()
            error_msg = "Username sudah digunakan." if err.errno == 1062 else f"Terjadi kesalahan saat registrasi: {err.msg}"
            flash(error_msg, 'error')
            return render_template('register.html')
        finally:
            if conn: conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear() 
    return redirect(url_for('login'))

# ----------------------------------------------------------------------
# RUTE APLIKASI UTAMA
# ----------------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    """Route Dashboard/Home"""
    conn = get_db_connection()
    total_detections = 0
    if conn:
        cursor = conn.cursor()
        user_id = session.get('user_id')
        try:
            sql = "SELECT COUNT(*) FROM hasil_deteksi WHERE id_user = %s"
            cursor.execute(sql, (user_id,))
            total_detections = cursor.fetchone()[0]
        except mysql.connector.Error as err:
            flash(f"Gagal memuat statistik: {err}", 'error')
        finally:
            conn.close()

    # Merender dashboard.html
    return render_template('dashboard.html', 
                            full_name=session.get('full_name'),
                            total_detections=total_detections)


@app.route('/utama')
@login_required
def utama():
    """Route Halaman Deteksi/Kamera - Mengambil hasil dari session"""
    # Mengambil dan MENGHAPUS data hasil dari session saat halaman dimuat
    # Ini memastikan hasil hanya ditampilkan sekali saat redirect dari /detect
    detection_result = session.pop('detection_result', None)
    detection_score = session.pop('detection_score', None)
    raw_score = session.pop('raw_score', None)
    image_path = session.pop('image_path', None)
    timestamp = session.pop('timestamp', None)
    timestamp_db = session.pop('timestamp_db', None)
    
    # Merender utama.html
    return render_template('utama.html', 
        full_name=session.get('full_name'),
        detection_result=detection_result, 
        detection_score=detection_score, 
        raw_score=raw_score,
        image_path=image_path,
        timestamp=timestamp,
        timestamp_db=timestamp_db
    )


@app.route('/detect', methods=['POST'])
@login_required
def detect():
    """Menangani proses deteksi gambar."""
    file_obj = None
    original_filename = None
    
    # --- 1. MEMPROSES INPUT FILE ATAU KAMERA ---
    if 'file' in request.files and request.files['file'].filename != '':
        file_storage = request.files['file']
        file_obj = io.BytesIO(file_storage.read())
        original_filename = file_storage.filename
    elif 'camera_data' in request.form and request.form['camera_data']:
        data_url = request.form['camera_data']
        # Pastikan format data URL benar sebelum dipecah
        if ',' not in data_url:
             flash("Format data kamera tidak valid.", 'error')
             return redirect(url_for('utama'))
             
        header, encoded = data_url.split(',', 1)
        try:
            image_data = base64.b64decode(encoded)
            file_obj = io.BytesIO(image_data)
            original_filename = f"capture_{uuid.uuid4().hex[:8]}.jpeg"
        except Exception as e:
            flash("Gagal mendekode data kamera.", 'error')
            return redirect(url_for('utama'))
    else:
        flash("Tidak ada file yang diunggah atau foto yang diambil.", 'error')
        return redirect(url_for('utama'))

    # --- 2. SIMPAN FILE LOKAL ---
    if file_obj:
        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
        image_path = save_local_file(file_obj, unique_filename) 
    else:
        flash("Gagal memproses file/foto.", 'error')
        return redirect(url_for('utama'))

    # --- 3. JALANKAN PREDIKSI AI ---
    if image_path:
        file_obj.seek(0)
        prediction = predict_defect(file_obj) 

        # --- 4. SIMPAN HASIL DI SESSION ---
        raw_score = prediction['score']
        
        session['detection_result'] = prediction['hasil']
        session['detection_score'] = f"{raw_score:.2f}%"
        session['raw_score'] = raw_score 
        session['image_path'] = image_path
        session['timestamp'] = datetime.now().strftime('%d %B %Y, %H:%M:%S') 
        session['timestamp_db'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') 
        
        # Redirect ke rute utama untuk menampilkan hasil dari session
        return redirect(url_for('utama'))
    
    flash("Terjadi kesalahan saat memproses deteksi.", 'error')
    return redirect(url_for('utama'))

@app.route('/save_detection', methods=['POST'])
@login_required
def save_detection():
    hasil = request.form.get('hasil')
    score_str = request.form.get('score')
    image_path = request.form.get('image_path')
    timestamp_db = request.form.get('timestamp_db')
    user_id = session.get('user_id')
    
    try:
        score = float(score_str)
    except (TypeError, ValueError):
        flash("Skor deteksi tidak valid.", 'error')
        return redirect(url_for('utama'))

    if not all([hasil, score_str, image_path, timestamp_db, user_id]):
        flash("Data hasil deteksi tidak lengkap untuk disimpan.", 'error')
        return redirect(url_for('utama'))

    conn = get_db_connection()
    if conn is None:
        flash("Kesalahan Koneksi Database saat menyimpan data.", 'error')
        return redirect(url_for('utama'))

    cursor = conn.cursor()
    try:
        sql = """INSERT INTO hasil_deteksi 
                 (id_user, id_gambar, hasil, score, tanggal_deteksi) 
                 VALUES (%s, %s, %s, %s, %s)"""
        # Perhatikan urutan dan tipe data parameter (float(score))
        cursor.execute(sql, (user_id, image_path, hasil, score, timestamp_db))
        conn.commit()
        
        flash("Hasil deteksi berhasil disimpan ke Riwayat!", 'success')
        return redirect(url_for('history'))
    except mysql.connector.Error as err:
        conn.rollback()
        flash(f"Terjadi kesalahan saat menyimpan data: {err}", 'error')
        return redirect(url_for('utama'))
    finally:
        if conn: conn.close()

@app.route('/history')
@login_required
def history():
    conn = get_db_connection()
    user_id = session.get('user_id')
    history_data = []
    error_message = None

    if conn is None:
        # Jika gagal koneksi, tampilkan pesan error yang jelas
        flash("Kesalahan Koneksi Database.", 'error')
    else:
        cursor = conn.cursor(dictionary=True) 
        try:
            # Query MySQL dengan format tanggal yang benar
            sql = """SELECT id_deteksi, id_gambar, hasil, score, 
                      DATE_FORMAT(tanggal_deteksi, '%d %b %Y, %H:%i:%s') as formatted_date
                      FROM hasil_deteksi 
                      WHERE id_user = %s 
                      ORDER BY tanggal_deteksi DESC"""
            # Parameter tunggal diberikan dalam tuple (user_id,)
            cursor.execute(sql, (user_id,)) 
            history_data = cursor.fetchall()
        except mysql.connector.Error as err:
            error_message = f"Kesalahan saat memuat data riwayat: {err}"
            flash(error_message, 'error') # Flash error database
        finally:
            if conn: conn.close()
    
    # Ambil semua flash messages untuk ditampilkan di template
    # Anda perlu mengulanginya di template HTML Anda
    return render_template('history.html', 
        full_name=session.get('full_name'),
        history_data=history_data
    )

@app.route('/delete/<int:id_deteksi>', methods=['POST'])
@login_required
def delete_detection(id_deteksi):
    user_id = session.get('user_id')
    conn = get_db_connection()

    if conn is None:
        flash("Kesalahan Koneksi Database saat menghapus data.", 'error')
        return redirect(url_for('history'))

    cursor = conn.cursor(dictionary=True)
    
    try:
        sql_select = "SELECT id_gambar FROM hasil_deteksi WHERE id_deteksi = %s AND id_user = %s"
        cursor.execute(sql_select, (id_deteksi, user_id))
        record = cursor.fetchone()

        if record:
            image_path_relative = record['id_gambar']
            image_path_full = os.path.join(app.root_path, 'static', image_path_relative)
            
            sql_delete = "DELETE FROM hasil_deteksi WHERE id_deteksi = %s AND id_user = %s"
            cursor.execute(sql_delete, (id_deteksi, user_id))
            conn.commit()

            # Hapus file fisik setelah berhasil dihapus dari DB
            if os.path.exists(image_path_full) and os.path.isfile(image_path_full):
                os.remove(image_path_full)
            
            flash("Hasil deteksi berhasil dihapus!", 'success')
            return redirect(url_for('history'))
        else:
            flash("Data riwayat tidak ditemukan atau Anda tidak memiliki akses.", 'error')
            return redirect(url_for('history'))

    except mysql.connector.Error as err:
        conn.rollback()
        flash(f"Kesalahan SQL saat menghapus: {err}", 'error')
        return redirect(url_for('history'))
    except Exception as e:
        flash(f"Kesalahan sistem saat menghapus file: {e}", 'error')
        return redirect(url_for('history'))
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    # Pastikan folder uploads ada
    if not os.path.exists(os.path.join('static', 'uploads')):
        os.makedirs(os.path.join('static', 'uploads'))
    app.run(debug=True)