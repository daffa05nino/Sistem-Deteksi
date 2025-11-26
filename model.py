# model.py

import tensorflow as tf
# HAPUS: from tensorflow.keras.models import load_model # (Gunakan jika model Anda sudah ada)
from tensorflow.keras.preprocessing import image
import numpy as np
from PIL import Image
import io
import os
from werkzeug.utils import secure_filename 

# --- Konfigurasi ---
MODEL_PATH = 'cnn_defect_detector.h5' 
IMG_SIZE = (224, 224) 
UPLOAD_FOLDER = 'uploads' 

# --- Fungsi Penyimpanan Lokal ---

def save_local_file(file_obj, filename, folder=UPLOAD_FOLDER):
    """Menyimpan file yang diunggah secara lokal ke direktori static/uploads."""
    
    upload_path = os.path.join('static', folder)
    
    # 1. Pastikan direktori ada
    if not os.path.exists(upload_path):
        os.makedirs(upload_path)
        
    # 2. Amankan nama file
    safe_filename = secure_filename(filename)
    file_path = os.path.join(upload_path, safe_filename)
    
    # 3. Simpan file
    file_obj.seek(0)
    with open(file_path, 'wb') as f:
        f.write(file_obj.read())
        
    # Mengembalikan path relatif ('uploads/file.jpg')
    return f'{folder}/{safe_filename}' 

# --- Fungsi Prediksi CNN (Menggunakan Placeholder jika model tidak ada) ---

def load_cnn_model():
    """Memuat model CNN."""
    if not os.path.exists(MODEL_PATH):
        print(f"WARNING: Model {MODEL_PATH} tidak ditemukan. Menggunakan hasil placeholder.")
        return None
    
    try:
        model = tf.keras.models.load_model(MODEL_PATH) 
        return model
    except Exception as e:
        print(f"Error loading model: {e}")
        return None

def predict_defect(file_obj):
    """Memproses gambar dan melakukan prediksi."""
    model = load_cnn_model()
    
    if model is None:
        # Placeholder result
        mock_score = np.random.uniform(70, 99) 
        hasil = "cacat" if mock_score > 85 else "tidak cacat"
        display_score = mock_score if hasil == "cacat" else 100 - mock_score
        return {"hasil": hasil, "score": round(display_score, 2)}
        
    try:
        # Load dan Prediksi (kode tetap sama seperti sebelumnya)
        img = Image.open(file_obj)
        img = img.resize(IMG_SIZE)
        img_array = image.img_to_array(img)
        img_array = np.expand_dims(img_array, axis=0)
        img_array = tf.keras.applications.mobilenet_v2.preprocess_input(img_array)

        prediction = model.predict(img_array)[0][0]
        score_percent = float(prediction * 100) 
        
        if score_percent >= 50:
            hasil = "cacat"
            display_score = score_percent
        else:
            hasil = "tidak cacat"
            display_score = 100 - score_percent
            
        return {"hasil": hasil, "score": round(display_score, 2)}
    except Exception as e:
        print(f"Error during actual prediction: {e}")
        return {"hasil": "ERROR", "score": 0.0}