let audioElements = {};
let isPlaying = false;
let currentTime = 0;
let currentTrackURLs = [];

// Recupera il nome della canzone dal template HTML
const songName = document.body.dataset.songName;

document.addEventListener("DOMContentLoaded", () => {
    const playBtn = document.getElementById("play-btn");
    const stopBtn = document.getElementById("stop-btn");
    const downloadBtn = document.getElementById("download-zip-btn");

    // Inizializza audio e slider
    const trackDivs = document.querySelectorAll(".track");
    trackDivs.forEach(div => {
        const track = div.querySelector("span").textContent.toLowerCase();
        const slider = div.querySelector("input[type='range']");
        const url = slider.dataset.url || slider.getAttribute("data-url");

        const audio = new Audio(url);
        audio.preload = "auto";
        audio.volume = parseFloat(slider.value);

        audio.addEventListener("timeupdate", () => {
            currentTime = audio.currentTime;
        });

        audio.addEventListener("ended", () => {
            highlightTrack(track, false);
            // Se tutte le tracce sono finite
            if (Object.values(audioElements).every(a => a.ended)) {
                isPlaying = false;
                playBtn.textContent = "▶ Play";
                deleteTracks(); // cancella tracce alla fine
            }
        });

        audioElements[track] = audio;
        currentTrackURLs.push(url);

        // Gestione volume slider
        slider.addEventListener("input", () => {
            audio.volume = parseFloat(slider.value);
        });
    });

    // Play / Pausa
    playBtn.addEventListener("click", () => {
        if (!isPlaying) {
            Object.entries(audioElements).forEach(([track, audio]) => {
                audio.currentTime = currentTime;
                audio.play();
                highlightTrack(track, true);
            });
            isPlaying = true;
            playBtn.textContent = "⏸ Pausa";
        } else {
            Object.entries(audioElements).forEach(([track, audio]) => {
                audio.pause();
                highlightTrack(track, false);
            });
            isPlaying = false;
            playBtn.textContent = "▶ Play";
        }
    });

    // Stop → solo pausa senza resettare il tempo
    stopBtn.addEventListener("click", () => {
        Object.entries(audioElements).forEach(([track, audio]) => {
            audio.pause();
            highlightTrack(track, false);
        });
        isPlaying = false;
        playBtn.textContent = "▶ Play";
    });

    // Download ZIP
    downloadBtn.addEventListener("click", () => {
        if (currentTrackURLs.length === 0) return;
        const zipUrl = "/download_zip?" + new URLSearchParams({
            tracks: JSON.stringify(currentTrackURLs)
        });
        window.location.href = zipUrl;
    });
});

// Evidenzia traccia
function highlightTrack(track, highlight) {
    const slider = document.getElementById(`vol-${track}`);
    if (!slider) return;
    if (highlight) {
        slider.parentElement.style.backgroundColor = "#00b4d8";
        slider.parentElement.style.color = "#fff";
    } else {
        slider.parentElement.style.backgroundColor = "#1f2937";
        slider.parentElement.style.color = "#fff";
    }
}

// Cancella tracce sul server
async function deleteTracks() {
    if (!songName) return;
    try {
        await fetch(`/delete/${songName}`, { method: "POST" });
        console.log(`Tracce ${songName} cancellate dal server`);
    } catch (e) {
        console.warn("Errore cancellazione tracce:", e);
    }
}

// Cancella tracce quando l'utente chiude o cambia pagina
window.addEventListener("beforeunload", deleteTracks);
