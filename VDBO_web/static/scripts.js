let audioElements = {};
let isPlaying = false;

document.addEventListener("DOMContentLoaded", () => {
    const uploadForm = document.getElementById("upload-form");
    const status = document.getElementById("status");
    const playerSection = document.getElementById("player-section");
    const playBtn = document.getElementById("play-btn");
    const stopBtn = document.getElementById("stop-btn");

    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        status.textContent = "Elaborazione in corso... ⏳ (può durare qualche minuto)";
        playerSection.classList.add("d-none");

        const file = document.getElementById("audio-file").files[0];
        const url = document.getElementById("youtube-url").value;

        const formData = new FormData();
        if (file) formData.append("file", file);
        if (url) formData.append("url", url);

        try {
            const res = await axios.post("/process", formData, {
                headers: { "Content-Type": "multipart/form-data" }
            });
            
            if (res.data.success) {
                status.textContent = "✅ Tracce pronte!";
                loadTracks(res.data.tracks);
                playerSection.classList.remove("d-none");
            } else {
                status.textContent = "❌ Errore durante l'elaborazione.";
            }
        } catch (err) {
            console.error(err);
            status.textContent = "❌ Errore server o file non valido.";
        }
    });

    playBtn.addEventListener("click", playAll);
    stopBtn.addEventListener("click", stopAll);

    // Slider volume
    ["vocals", "drums", "bass", "other"].forEach(track => {
        const slider = document.getElementById(`vol-${track}`);
        slider.addEventListener("input", () => {
            if (audioElements[track]) {
                audioElements[track].volume = parseFloat(slider.value);
            }
        });
    });
});

function loadTracks(tracks) {
    audioElements = {};
    ["vocals", "drums", "bass", "other"].forEach(track => {
        if (tracks[track]) {
            const audio = new Audio(tracks[track]);
            audio.volume = 0.8;
            audioElements[track] = audio;
        }
    });
}

function playAll() {
    if (isPlaying) return;
    const startTime = audioElements.vocals?.currentTime || 0;

    Object.values(audioElements).forEach(a => {
        a.currentTime = startTime;
        a.play();
    });
    isPlaying = true;
}

function stopAll() {
    Object.values(audioElements).forEach(a => {
        a.pause();
        a.currentTime = 0;
    });
    isPlaying = false;
}
