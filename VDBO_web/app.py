import os
import shutil
import subprocess
import uuid
import yt_dlp
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory

# =============================================================================
# CONFIGURAZIONE BASE
# =============================================================================
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "static/output"
MAX_OUTPUT_FOLDERS = 10

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# FUNZIONE: pulizia cartelle vecchie
# =============================================================================
def cleanup_old_outputs(base_dir, max_folders=10):
    """Cancella le cartelle più vecchie in base alla data di modifica"""
    folders = []
    for name in os.listdir(base_dir):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path):
            folders.append((path, os.path.getmtime(path)))

    folders.sort(key=lambda x: x[1])
    if len(folders) > max_folders:
        to_delete = folders[:-max_folders]
        for folder, _ in to_delete:
            try:
                shutil.rmtree(folder)
                logger.info(f"🧹 Rimossa cartella vecchia: {folder}")
            except Exception as e:
                logger.warning(f"⚠️ Errore rimuovendo {folder}: {e}")

# =============================================================================
# FUNZIONE: scarica audio da YouTube
# =============================================================================
def download_youtube_audio(url, output_dir):
    """Scarica la traccia audio da un link YouTube in formato WAV"""
    output_path = os.path.join(output_dir, "%(title)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "192"}],
        "quiet": True,
        "noplaylist": True
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
# FUNZIONI AUDIO UTILI
# =============================================================================
def get_audio_duration(file_path):
    try:
        import wave
        if file_path.endswith('.wav'):
            with wave.open(file_path, 'r') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                return frames / float(rate)
    except:
        pass
    return 180

# =============================================================================
# FUNZIONE: separa le tracce con Demucs (4 stems)
# =============================================================================
def separate_with_demucs(input_file, output_dir, model="mdx_extra_q"):
    """Separazione Demucs in 4 tracce, output in unica cartella pulita"""
    try:
        if not os.path.exists(input_file):
            logger.error(f"File input non trovato: {input_file}")
            return None

        # Cartella pulita per questa elaborazione
        song_folder = os.path.join(output_dir, str(uuid.uuid4()))
        os.makedirs(song_folder, exist_ok=True)

        cmd = ['demucs', '-n', model, '--out', song_folder, input_file]
        logger.info(f"Esecuzione: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=1200)

        # Cerca la cartella generata dal modello
        separated_files = {}
        for root, dirs, files in os.walk(song_folder):
            for file in files:
                if file.endswith(".wav"):
                    track_name = file.replace(".wav", "")
                    if track_name in ["vocals", "drums", "bass", "other"]:
                        separated_files[track_name] = os.path.join(root, file)

        if not separated_files:
            logger.error("❌ Nessuna traccia valida trovata")
            return None

        return separated_files

    except subprocess.CalledProcessError as e:
        logger.error(f"[Demucs ERROR] {e}")
        return None
    except subprocess.TimeoutExpired:
        logger.error("Timeout Demucs (troppo lungo)")
        return None
    except Exception as e:
        logger.error(f"Errore separazione: {e}")
        return None

# =============================================================================
# ROUTE: pagina principale
# =============================================================================
@app.route("/")
def index():
    return render_template("index.html")

# =============================================================================
# ROUTE: processa file o URL YouTube
# =============================================================================
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
        return jsonify({"success": False, "error": "Nessun file o URL fornito"}), 400

    if not audio_path or not os.path.exists(audio_path):
        return jsonify({"success": False, "error": "Errore nel download o caricamento"}), 500

    # Separazione
    result_files = separate_with_demucs(audio_path, OUTPUT_FOLDER)
    if not result_files:
        return jsonify({"success": False, "error": "Errore nella separazione audio"}), 500

    cleanup_old_outputs(OUTPUT_FOLDER, MAX_OUTPUT_FOLDERS)

    # Costruisci i link pubblici
    track_urls = {}
    for track, path in result_files.items():
        if os.path.exists(path):
            track_urls[track] = f"/{path.replace(os.sep, '/')}"

    return jsonify({"success": True, "tracks": track_urls})

# =============================================================================
# ROUTE: serve file statici
# =============================================================================
@app.route("/static/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("🚀 Avvio server Flask su http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
