import os
import shutil
import subprocess
import uuid
import yt_dlp
import logging
import zipfile
import tempfile
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file, jsonify

# =============================================================================
# CONFIGURAZIONE BASE
# =============================================================================
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "static/output"
MAX_OUTPUT_FOLDERS = 10

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("VDBO")

# =============================================================================
# FUNZIONI DI PULIZIA
# =============================================================================
def cleanup_old_outputs(base_dir, max_folders=10):
    folders = [(os.path.join(base_dir, f), os.path.getmtime(os.path.join(base_dir, f)))
               for f in os.listdir(base_dir)
               if os.path.isdir(os.path.join(base_dir, f))]
    folders.sort(key=lambda x: x[1])
    if len(folders) > max_folders:
        for folder, _ in folders[:-max_folders]:
            try:
                shutil.rmtree(folder)
                logger.info(f"🧹 Rimossa cartella vecchia: {folder}")
            except Exception as e:
                logger.warning(f"⚠️ Errore rimuovendo {folder}: {e}")

def delete_upload_folder(temp_id):
    work_dir = os.path.join(UPLOAD_FOLDER, temp_id)
    if os.path.exists(work_dir):
        try:
            shutil.rmtree(work_dir)
            logger.info(f"🗑️ Cartella di upload cancellata: {work_dir}")
        except Exception as e:
            logger.warning(f"⚠️ Errore cancellando {work_dir}: {e}")

def delete_output_folder(song_name):
    song_dir = os.path.join(OUTPUT_FOLDER, song_name)
    if os.path.exists(song_dir):
        try:
            shutil.rmtree(song_dir)
            logger.info(f"🗑️ Tracce di {song_name} cancellate")
        except Exception as e:
            logger.warning(f"⚠️ Errore cancellando {song_dir}: {e}")

# =============================================================================
# DOWNLOAD AUDIO DA YOUTUBE
# =============================================================================
def download_youtube_audio(url, output_dir):
    output_path = os.path.join(output_dir, "%(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "192"}],
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/117.0.0.0 Safari/537.36"
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            wav_file = os.path.splitext(filename)[0] + ".wav"
            return wav_file if os.path.exists(wav_file) else None
    except Exception as e:
        logger.error(f"[YouTube ERROR] {e}")
        return None

# =============================================================================
# DEMUCS SEPARATION
# =============================================================================
def separate_with_demucs(input_file, output_dir, model="htdemucs"):
    song_name = os.path.splitext(os.path.basename(input_file))[0]
    clean_output_dir = os.path.join(output_dir, song_name)
    if os.path.exists(clean_output_dir):
        shutil.rmtree(clean_output_dir)
    os.makedirs(clean_output_dir, exist_ok=True)

    logger.info(f"Separazione di: {song_name}")
    cmd = ['demucs', '-n', model, '--out', output_dir, input_file]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if result.returncode != 0:
        logger.error(f"Errore Demucs (code {result.returncode})")
        logger.error(f"STDERR: {result.stderr}")
        return None

    model_dir = os.path.join(output_dir, model)
    found_path = None
    for item in os.listdir(model_dir):
        if song_name.lower() in item.lower():
            candidate = os.path.join(model_dir, item)
            if os.path.isdir(candidate):
                found_path = candidate
                break
    if not found_path:
        logger.error("Cartella output Demucs non trovata")
        return None

    separated_files = {}
    for file in os.listdir(found_path):
        if file.endswith(".wav") and not file.startswith("no_vocals"):
            src = os.path.join(found_path, file)
            dst = os.path.join(clean_output_dir, file)
            shutil.copy2(src, dst)
            separated_files[file.replace(".wav", "")] = dst

    shutil.rmtree(model_dir, ignore_errors=True)
    logger.info(f"✅ Tracce salvate in: {clean_output_dir}")
    return separated_files if separated_files else None

# =============================================================================
# ROUTES
# =============================================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    temp_id = str(uuid.uuid4())
    work_dir = os.path.join(UPLOAD_FOLDER, temp_id)
    os.makedirs(work_dir, exist_ok=True)

    audio_path = None
    if "file" in request.files and request.files["file"].filename != "":
        file = request.files["file"]
        filename = file.filename
        audio_path = os.path.join(work_dir, filename)
        file.save(audio_path)
    elif "url" in request.form and request.form["url"].strip() != "":
        url = request.form["url"].strip()
        audio_path = download_youtube_audio(url, work_dir)
    else:
        return "Nessun file o URL fornito", 400

    if not audio_path or not os.path.exists(audio_path):
        return "Errore nel caricamento o nel download", 500

    model = request.form.get("model", "htdemucs")
    result_files = separate_with_demucs(audio_path, OUTPUT_FOLDER, model=model)
    if not result_files:
        return "Errore durante la separazione", 500

    cleanup_old_outputs(OUTPUT_FOLDER, MAX_OUTPUT_FOLDERS)

    song_name = os.path.splitext(os.path.basename(audio_path))[0]
    return redirect(url_for("track_page", song_name=song_name, temp_id=temp_id))

@app.route("/tracks/<song_name>")
def track_page(song_name):
    temp_id = request.args.get("temp_id", "")
    song_dir = os.path.join(OUTPUT_FOLDER, song_name)
    if not os.path.exists(song_dir):
        return "Tracce non trovate", 404

    tracks = {f.replace(".wav",""): f"/static/output/{song_name}/{f}" 
              for f in os.listdir(song_dir) if f.endswith(".wav")}
    return render_template("tracks.html", song_name=song_name, tracks=tracks, temp_id=temp_id)

@app.route("/delete/<song_name>/<temp_id>", methods=["POST"])
def delete_all(song_name, temp_id):
    delete_output_folder(song_name)
    delete_upload_folder(temp_id)
    return jsonify({"success": True})

@app.route("/download_zip")
def download_zip():
    import json
    track_list = request.args.get("tracks")
    if not track_list:
        return "Nessuna traccia fornita", 400
    try:
        tracks = json.loads(track_list)
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        with zipfile.ZipFile(temp_zip.name, 'w') as zipf:
            for t in tracks:
                file_path = t.lstrip("/")
                if os.path.exists(file_path):
                    zipf.write(file_path, os.path.basename(file_path))
        return send_file(temp_zip.name, as_attachment=True, download_name="VDBO_tracks.zip")
    except Exception as e:
        logger.error(f"Errore creazione ZIP: {e}")
        return "Errore nel creare l'archivio ZIP", 500

@app.route("/static/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("🚀 Avvio VDBO su http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
