// Improved player initialization for Musify — polished controls, per-track progress and cover fetch
document.addEventListener('DOMContentLoaded', () => {
    // Force dark theme by default
    document.documentElement.classList.add('dark');
    localStorage.setItem('musify_theme', 'dark');
    const playlist = document.getElementById('playlist');
    const audio = document.getElementById('audio');
    const playBtn = document.getElementById('playBtn');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const artwork = document.getElementById('artwork');
    const trackTitle = document.getElementById('track-title');
    const trackArtist = document.getElementById('track-artist');
    const progressBar = document.getElementById('progress-bar');
    const progressContainer = document.getElementById('progress-bar-container');
    const currentTimeEl = document.getElementById('currentTime');
    const durationEl = document.getElementById('duration');
    const themeToggle = document.getElementById('themeToggle');

    if (!playlist || !audio) {
        console.warn('Player elements missing; player disabled.');
        return;
    }

    let tracks = Array.from(playlist.querySelectorAll('li[data-src]'));
    let currentIndex = -1;
    let isPlaying = false;

    // Theme handling: persist preference in localStorage
    function applyTheme(dark) {
        if (dark) document.documentElement.classList.add('dark');
        else document.documentElement.classList.remove('dark');
    }
    try {
        const saved = localStorage.getItem('musify_theme');
        applyTheme(saved === 'dark');
    } catch (err) {}
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const isDark = document.documentElement.classList.toggle('dark');
            try { localStorage.setItem('musify_theme', isDark ? 'dark' : 'light'); } catch (e) {}
        });
    }

    // nicer SVG icons injection for the main controls
    function icon(name) {
        const icons = {
            play: '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
            pause: '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M6 19h4V5H6zm8-14v14h4V5z"/></svg>',
            prev: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M11 18V6l-8 6 8 6zm2-12v12h2V6h-2z"/></svg>',
            next: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M3 6v12l8-6-8-6zm10 0v12l8-6-8-6z"/></svg>'
        };
        return icons[name] || '';
    }

    // Make central play button large and set icons (icons inherit currentColor)
    if (playBtn) {
        playBtn.classList.add('play-large');
        playBtn.style.color = 'inherit';
        playBtn.innerHTML = icon('play');
    }
    if (prevBtn) prevBtn.innerHTML = icon('prev');
    if (nextBtn) nextBtn.innerHTML = icon('next');

    function formatTime(seconds) {
        if (!isFinite(seconds)) return '0:00';
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s < 10 ? '0' : ''}${s}`;
    }

    function loadTrack(index) {
        if (index < 0 || index >= tracks.length) return;
        const li = tracks[index];
        const src = li.dataset.src;
        const title = li.dataset.title || 'Unknown';
        const file = li.dataset.file;

        audio.src = src;
        trackTitle.textContent = title;
        trackArtist.textContent = '';
        artwork.src = '/cover/' + encodeURIComponent(file);
        currentIndex = index;
        highlightCurrent();
    }

    function highlightCurrent() {
        tracks.forEach((t, i) => t.classList.toggle('active', i === currentIndex));
    }

    // update per-item mini-progress bar smoothly
    function updateMiniProgress() {
        tracks.forEach((t, i) => {
            const bar = t.querySelector('.mini-progress-bar');
            if (!bar) return;
            if (i === currentIndex && audio.duration) {
                const pct = (audio.currentTime / audio.duration) * 100;
                bar.style.width = pct + '%';
                bar.style.opacity = '1';
            } else {
                // faded indicator for other tracks
                bar.style.width = '0%';
                bar.style.opacity = '0.25';
            }
        });
    }

    playlist.addEventListener('click', (e) => {
        const li = e.target.closest('li[data-src]');
        if (!li) return;
        const index = tracks.indexOf(li);
        if (index !== -1) {
            loadTrack(index);
            play();
        }
    });

    function play() {
        if (!audio.src) return;
        const p = audio.play();
        if (p && p.then) {
            p.then(() => {
                isPlaying = true;
                if (playBtn) playBtn.innerHTML = icon('pause');
            }).catch((err) => {
                console.warn('Playback failed:', err);
            });
        } else {
            isPlaying = true;
            if (playBtn) playBtn.innerHTML = icon('pause');
        }
    }

    function pause() {
        audio.pause();
        isPlaying = false;
        if (playBtn) playBtn.innerHTML = icon('play');
    }

    if (playBtn) playBtn.addEventListener('click', () => {
        if (!audio.src && tracks.length) {
            loadTrack(0);
        }
        if (isPlaying) pause(); else play();
    });

    if (prevBtn) prevBtn.addEventListener('click', () => {
        if (tracks.length === 0) return;
        const idx = currentIndex > 0 ? currentIndex - 1 : tracks.length - 1;
        loadTrack(idx);
        play();
    });

    if (nextBtn) nextBtn.addEventListener('click', () => {
        if (tracks.length === 0) return;
        const idx = currentIndex < tracks.length - 1 ? currentIndex + 1 : 0;
        loadTrack(idx);
        play();
    });

    let rafId = null;

    audio.addEventListener('timeupdate', () => {
        if (!audio.duration) return;
        const percent = (audio.currentTime / audio.duration) * 100;
        if (progressBar) progressBar.style.width = percent + '%';
        if (currentTimeEl) currentTimeEl.textContent = formatTime(audio.currentTime);
        if (durationEl) durationEl.textContent = formatTime(audio.duration);
        updateMiniProgress();
    });

    audio.addEventListener('loadedmetadata', () => {
        if (durationEl) durationEl.textContent = formatTime(audio.duration);
        updateMiniProgress();
    });

    audio.addEventListener('ended', () => {
        // auto-advance
        const idx = currentIndex < tracks.length - 1 ? currentIndex + 1 : 0;
        loadTrack(idx);
        play();
    });

    // nicer seeking: click or drag
    if (progressContainer) {
        let seeking = false;
        const seek = (clientX) => {
            const rect = progressContainer.getBoundingClientRect();
            const x = Math.min(Math.max(0, clientX - rect.left), rect.width);
            const pct = x / rect.width;
            if (audio.duration) audio.currentTime = pct * audio.duration;
        };

        progressContainer.addEventListener('pointerdown', (e) => {
            seeking = true;
            progressContainer.setPointerCapture(e.pointerId);
            seek(e.clientX);
        });
        progressContainer.addEventListener('pointermove', (e) => {
            if (seeking) seek(e.clientX);
        });
        progressContainer.addEventListener('pointerup', (e) => {
            seeking = false;
            try { progressContainer.releasePointerCapture(e.pointerId); } catch (err) {}
        });
    }

    // keyboard shortcuts: space play/pause, left/right seek
    document.addEventListener('keydown', (e) => {
        if (e.code === 'Space') {
            if (e.target && (e.target.tagName === 'INPUT' || e.target.isContentEditable)) return;
            e.preventDefault();
            if (isPlaying) pause(); else play();
        } else if (e.code === 'ArrowRight') {
            audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 10);
        } else if (e.code === 'ArrowLeft') {
            audio.currentTime = Math.max(0, audio.currentTime - 10);
        }
    });

    // initial load if any
    if (tracks.length) {
        loadTrack(0);
    }
});
