from flask import Flask, render_template, request, Response, send_from_directory, send_file, jsonify
import os, json, threading, requests, re
import yt_dlp
from queue import Queue
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
import io
from flask_socketio import SocketIO, emit, join_room, leave_room
from functools import lru_cache
import time
from datetime import datetime
from collections import defaultdict
import math
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'lamgerrsmusify654'

# ========================================
# ON_HOST MODE CONFIGURATION
# ========================================
# Set to True when hosting publicly - shows trending songs from YouTube
# Set to False for local/personal use - uses local music library
ON_HOST = os.environ.get('ON_HOST', 'false').lower() == 'true'
DEMO_PLAY_DURATION = 30  # Seconds - shortened play time when ON_HOST is True

DOWNLOAD_FOLDER = '../../Music/'
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['ON_HOST'] = ON_HOST
app.config['DEMO_PLAY_DURATION'] = DEMO_PLAY_DURATION
PREFERENCES_FILE = os.path.join(DOWNLOAD_FOLDER, '.musify_preferences.json')

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Use a dict to store progress queues per session
progress_queues = {}

# Artwork cache with TTL (time-to-live)
artwork_cache = {}
ARTWORK_CACHE_TTL = 300  # 5 minutes

# ========================================
# MUSIC RECOMMENDATION ENGINE
# ========================================

class MusicRecommendationEngine:
    """
    Smart music recommendation engine that learns user preferences.
    Tracks: play count, completion rate, skips, time of day, and extracts
    features from song names to build preference profiles.
    """
    
    def __init__(self, preferences_file):
        self.preferences_file = preferences_file
        self.data = self._load_preferences()
    
    def _load_preferences(self):
        """Load preferences from file or create default structure."""
        default = {
            'song_stats': {},  # Per-song statistics
            'keyword_scores': {},  # Learned keyword preferences
            'artist_scores': {},  # Learned artist preferences
            'time_preferences': {str(h): {} for h in range(24)},  # Hour-based preferences
            'genre_hints': {},  # Genre-like patterns
            'total_plays': 0,
            'total_skips': 0,
            'learning_rate': 0.1,
            'last_updated': None
        }
        try:
            if os.path.exists(self.preferences_file):
                with open(self.preferences_file, 'r') as f:
                    loaded = json.load(f)
                    # Merge with defaults for any missing keys
                    for key in default:
                        if key not in loaded:
                            loaded[key] = default[key]
                    return loaded
        except Exception as e:
            print(f"Error loading preferences: {e}")
        return default
    
    def _save_preferences(self):
        """Save preferences to file."""
        try:
            self.data['last_updated'] = datetime.now().isoformat()
            with open(self.preferences_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"Error saving preferences: {e}")
    
    def _extract_features(self, song_name):
        """Extract features from a song name for learning."""
        # Remove file extension and clean up
        name = os.path.splitext(song_name)[0]
        name_lower = name.lower()
        
        features = {
            'keywords': [],
            'artist': None,
            'potential_genre': [],
            'mood_hints': [],
            'language_hints': []
        }
        
        # Common separators for artist - title
        if ' - ' in name:
            parts = name.split(' - ', 1)
            features['artist'] = parts[0].strip()
            name_lower = parts[1].lower() if len(parts) > 1 else name_lower
        elif ' by ' in name_lower:
            parts = name_lower.split(' by ', 1)
            features['artist'] = parts[1].strip() if len(parts) > 1 else None
        
        # Extract keywords (3+ character words)
        words = re.split(r'[\s\-_\.\(\)\[\],&]+', name_lower)
        features['keywords'] = [w.strip() for w in words if len(w.strip()) >= 3]
        
        # Genre hints based on common patterns
        genre_patterns = {
            'electronic': ['remix', 'edm', 'house', 'techno', 'dubstep', 'trance', 'bass', 'drop', 'beat'],
            'hiphop': ['rap', 'hip', 'hop', 'trap', 'flow', 'bars', 'cypher', 'freestyle'],
            'rock': ['rock', 'metal', 'guitar', 'punk', 'grunge', 'alternative'],
            'pop': ['pop', 'dance', 'party', 'club', 'hit'],
            'classical': ['symphony', 'orchestra', 'classical', 'piano', 'violin', 'opus'],
            'jazz': ['jazz', 'blues', 'swing', 'soul', 'funk'],
            'ambient': ['ambient', 'chill', 'relax', 'calm', 'peaceful', 'meditation', 'sleep'],
            'indian': ['bollywood', 'hindi', 'punjabi', 'desi', 'bhangra', 'indian'],
            'lofi': ['lofi', 'lo-fi', 'study', 'beats', 'aesthetic'],
            'acoustic': ['acoustic', 'unplugged', 'live', 'cover']
        }
        
        for genre, patterns in genre_patterns.items():
            for pattern in patterns:
                if pattern in name_lower:
                    features['potential_genre'].append(genre)
                    break
        
        # Mood hints
        mood_patterns = {
            'energetic': ['energy', 'hype', 'fire', 'lit', 'party', 'dance', 'fast', 'power'],
            'sad': ['sad', 'cry', 'tears', 'alone', 'lonely', 'heartbreak', 'broken', 'miss'],
            'happy': ['happy', 'joy', 'smile', 'love', 'sunshine', 'good', 'best'],
            'romantic': ['love', 'romance', 'heart', 'kiss', 'forever', 'baby', 'darling'],
            'motivational': ['motivation', 'inspire', 'dream', 'rise', 'success', 'champion', 'win']
        }
        
        for mood, patterns in mood_patterns.items():
            for pattern in patterns:
                if pattern in name_lower:
                    features['mood_hints'].append(mood)
                    break
        
        return features
    
    def record_play(self, song_name, completed=True, duration_played=0, total_duration=0, skipped=False):
        """Record a song play event for learning."""
        features = self._extract_features(song_name)
        current_hour = str(datetime.now().hour)
        
        # Initialize song stats if not exists
        if song_name not in self.data['song_stats']:
            self.data['song_stats'][song_name] = {
                'play_count': 0,
                'skip_count': 0,
                'total_completion': 0,
                'features': features,
                'first_played': datetime.now().isoformat(),
                'last_played': None
            }
        
        stats = self.data['song_stats'][song_name]
        stats['play_count'] += 1
        stats['last_played'] = datetime.now().isoformat()
        self.data['total_plays'] += 1
        
        if skipped:
            stats['skip_count'] += 1
            self.data['total_skips'] += 1
            reward = -0.3  # Negative reward for skip
        else:
            # Calculate completion ratio
            if total_duration > 0:
                completion = min(1.0, duration_played / total_duration)
            else:
                completion = 1.0 if completed else 0.5
            stats['total_completion'] += completion
            reward = completion * 0.5 + (0.5 if completed else 0)
        
        # Update keyword scores
        lr = self.data['learning_rate']
        for keyword in features['keywords']:
            if keyword not in self.data['keyword_scores']:
                self.data['keyword_scores'][keyword] = 0.5
            self.data['keyword_scores'][keyword] += lr * (reward - 0.5)
            self.data['keyword_scores'][keyword] = max(0, min(1, self.data['keyword_scores'][keyword]))
        
        # Update artist scores
        if features['artist']:
            artist = features['artist'].lower()
            if artist not in self.data['artist_scores']:
                self.data['artist_scores'][artist] = 0.5
            self.data['artist_scores'][artist] += lr * (reward - 0.3)
            self.data['artist_scores'][artist] = max(0, min(1, self.data['artist_scores'][artist]))
        
        # Update genre hints
        for genre in features['potential_genre']:
            if genre not in self.data['genre_hints']:
                self.data['genre_hints'][genre] = 0.5
            self.data['genre_hints'][genre] += lr * (reward - 0.5)
            self.data['genre_hints'][genre] = max(0, min(1, self.data['genre_hints'][genre]))
        
        # Update time preferences
        for keyword in features['keywords'][:5]:  # Top 5 keywords
            if keyword not in self.data['time_preferences'][current_hour]:
                self.data['time_preferences'][current_hour][keyword] = 0
            self.data['time_preferences'][current_hour][keyword] += 1
        
        self._save_preferences()
        return {'success': True, 'reward': reward}
    
    def calculate_song_score(self, song_name):
        """Calculate a preference score for a song based on learned patterns."""
        features = self._extract_features(song_name)
        current_hour = str(datetime.now().hour)
        
        score = 0.5  # Base score
        score_components = {}
        
        # Keyword matching score
        keyword_score = 0
        keyword_count = 0
        for keyword in features['keywords']:
            if keyword in self.data['keyword_scores']:
                keyword_score += self.data['keyword_scores'][keyword]
                keyword_count += 1
        if keyword_count > 0:
            keyword_score = keyword_score / keyword_count
            score_components['keywords'] = keyword_score
            score += (keyword_score - 0.5) * 0.3
        
        # Artist score
        if features['artist']:
            artist = features['artist'].lower()
            if artist in self.data['artist_scores']:
                artist_score = self.data['artist_scores'][artist]
                score_components['artist'] = artist_score
                score += (artist_score - 0.5) * 0.25
        
        # Genre score
        if features['potential_genre']:
            genre_score = 0
            for genre in features['potential_genre']:
                if genre in self.data['genre_hints']:
                    genre_score += self.data['genre_hints'][genre]
            genre_score = genre_score / len(features['potential_genre'])
            score_components['genre'] = genre_score
            score += (genre_score - 0.5) * 0.2
        
        # Time-based boost
        time_boost = 0
        time_prefs = self.data['time_preferences'].get(current_hour, {})
        for keyword in features['keywords']:
            if keyword in time_prefs:
                time_boost += time_prefs[keyword]
        if time_boost > 0:
            score += min(0.1, time_boost / 100)  # Cap time boost
        
        # Play history factor
        if song_name in self.data['song_stats']:
            stats = self.data['song_stats'][song_name]
            play_count = stats['play_count']
            skip_ratio = stats['skip_count'] / max(1, play_count)
            
            # Boost for songs played multiple times but not too much (avoid repetition)
            if play_count > 0:
                familiarity_boost = math.log(play_count + 1) * 0.05
                score += min(0.15, familiarity_boost)
            
            # Penalty for frequently skipped songs
            score -= skip_ratio * 0.2
            
            # Average completion bonus
            if play_count > 0:
                avg_completion = stats['total_completion'] / play_count
                score_components['completion'] = avg_completion
                score += (avg_completion - 0.5) * 0.15
        
        # Ensure score is between 0 and 1
        score = max(0, min(1, score))
        
        return {
            'score': score,
            'components': score_components,
            'features': features
        }
    
    def get_smart_shuffle_order(self, songs):
        """
        Get a smart shuffle order that prioritizes preferred songs.
        Creates two lists: likely-to-enjoy and others, then interleaves them smartly.
        """
        if not songs:
            return []
        
        # Calculate scores for all songs
        scored_songs = []
        for song in songs:
            score_data = self.calculate_song_score(song)
            scored_songs.append({
                'name': song,
                'score': score_data['score'],
                'data': score_data
            })
        
        # Sort by score
        scored_songs.sort(key=lambda x: x['score'], reverse=True)
        
        # Divide into preferred (top 50%) and others
        mid = len(scored_songs) // 2
        preferred = scored_songs[:max(1, mid)]
        others = scored_songs[mid:]
        
        # Shuffle within each group
        random.shuffle(preferred)
        random.shuffle(others)
        
        # Smart interleaving: 2-3 preferred songs, then 1 other, with randomness
        result = []
        pref_idx = 0
        other_idx = 0
        
        while pref_idx < len(preferred) or other_idx < len(others):
            # Add 2-3 preferred songs
            pref_count = random.randint(2, 3)
            for _ in range(pref_count):
                if pref_idx < len(preferred):
                    result.append(preferred[pref_idx])
                    pref_idx += 1
            
            # Add 1 other song (for discovery)
            if other_idx < len(others):
                result.append(others[other_idx])
                other_idx += 1
        
        return result
    
    def get_download_recommendations(self, count=5):
        """
        Generate download recommendations based on learned preferences.
        Returns search queries for songs the user might like.
        """
        recommendations = []
        
        # Get top keywords
        top_keywords = sorted(
            self.data['keyword_scores'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Get top artists
        top_artists = sorted(
            self.data['artist_scores'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # Get top genres
        top_genres = sorted(
            self.data['genre_hints'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        # Generate recommendations based on artists
        for artist, score in top_artists[:3]:
            if score > 0.55:
                recommendations.append({
                    'query': f"{artist} popular songs",
                    'reason': f"You seem to enjoy {artist.title()}",
                    'confidence': score,
                    'type': 'artist'
                })
        
        # Generate recommendations based on genres
        for genre, score in top_genres:
            if score > 0.55:
                genre_queries = {
                    'electronic': 'best electronic dance music 2024',
                    'hiphop': 'top hip hop rap songs',
                    'rock': 'best rock songs playlist',
                    'pop': 'top pop hits 2024',
                    'classical': 'beautiful classical music pieces',
                    'jazz': 'best jazz songs relaxing',
                    'ambient': 'chill ambient music relax',
                    'indian': 'top bollywood hindi songs',
                    'lofi': 'lofi hip hop beats study',
                    'acoustic': 'acoustic covers popular songs'
                }
                recommendations.append({
                    'query': genre_queries.get(genre, f"best {genre} music"),
                    'reason': f"Based on your {genre} listening patterns",
                    'confidence': score,
                    'type': 'genre'
                })
        
        # Generate recommendations based on keyword combinations
        if len(top_keywords) >= 2:
            strong_keywords = [k for k, s in top_keywords if s > 0.6][:3]
            if strong_keywords:
                query = ' '.join(strong_keywords[:2]) + ' songs'
                recommendations.append({
                    'query': query,
                    'reason': f"Based on your interest in {', '.join(strong_keywords[:2])}",
                    'confidence': 0.7,
                    'type': 'keywords'
                })
        
        # Time-based recommendations
        current_hour = datetime.now().hour
        if 22 <= current_hour or current_hour < 6:
            recommendations.append({
                'query': 'calm relaxing night music',
                'reason': 'Perfect for late night listening',
                'confidence': 0.6,
                'type': 'time'
            })
        elif 6 <= current_hour < 10:
            recommendations.append({
                'query': 'morning motivation music energetic',
                'reason': 'Great for starting your day',
                'confidence': 0.6,
                'type': 'time'
            })
        
        # Sort by confidence and return top recommendations
        recommendations.sort(key=lambda x: x['confidence'], reverse=True)
        return recommendations[:count]
    
    def get_preference_summary(self):
        """Get a summary of learned preferences for display."""
        top_artists = sorted(
            self.data['artist_scores'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        top_genres = sorted(
            self.data['genre_hints'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        top_keywords = sorted(
            self.data['keyword_scores'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Most played songs
        most_played = sorted(
            self.data['song_stats'].items(),
            key=lambda x: x[1].get('play_count', 0),
            reverse=True
        )[:5]
        
        return {
            'total_plays': self.data['total_plays'],
            'total_skips': self.data['total_skips'],
            'top_artists': [{'name': a, 'score': round(s, 2)} for a, s in top_artists if s > 0.4],
            'top_genres': [{'name': g, 'score': round(s, 2)} for g, s in top_genres if s > 0.4],
            'top_keywords': [{'name': k, 'score': round(s, 2)} for k, s in top_keywords if s > 0.5],
            'most_played': [{'name': n, 'plays': d['play_count']} for n, d in most_played],
            'learning_progress': min(100, self.data['total_plays'] * 2)  # % indicator
        }
    
    def reset_preferences(self):
        """Reset all learned preferences."""
        self.data = {
            'song_stats': {},
            'keyword_scores': {},
            'artist_scores': {},
            'time_preferences': {str(h): {} for h in range(24)},
            'genre_hints': {},
            'total_plays': 0,
            'total_skips': 0,
            'learning_rate': 0.1,
            'last_updated': None
        }
        self._save_preferences()


# Initialize the recommendation engine
recommendation_engine = MusicRecommendationEngine(PREFERENCES_FILE)


# Live Radio State
radio_state = {
    'is_live': False,
    'host_sid': None,
    'current_track': None,
    'current_time': 0,
    'is_playing': False,
    'listeners': 0,
    'track_info': {
        'title': '',
        'artist': '',
        'cover': ''
    }
}

def sanitize_filename(name):
    """Removes invalid characters for file systems."""
    return "".join(c for c in name if c.isalnum() or c in " _-").rstrip()

def parse_batch_songs(input_str):
    """Parse batch song input like [song1][song2][song3] or just a single song name."""
    # Match pattern [song1][song2]...
    pattern = r'\[([^\]]+)\]'
    matches = re.findall(pattern, input_str)
    if matches:
        return [s.strip() for s in matches if s.strip()]
    # If no brackets, treat as single song
    return [input_str.strip()] if input_str.strip() else []

def search_and_download_youtube(song_name, queue, song_index=1, total_songs=1, online_mode=False):
    def progress_hook(d):
        if d['status'] == 'downloading':
            progress_info = {
                'type': 'progress',
                'song_index': song_index,
                'total_songs': total_songs,
                'song_name': song_name,
                'progress_str': d.get('_percent_str', '0%'),
                'eta': d.get('_eta_str', 'N/A'),
            }
            queue.put(json.dumps(progress_info))
        elif d['status'] == 'finished':
            queue.put(json.dumps({
                'type': 'log',
                'message': f'[{song_index}/{total_songs}] Converting {song_name} to MP3...'
            }))

    ydl_opts = {
        'format': 'bestaudio/best',
        'default_search': 'ytsearch1',
        'noplaylist': True,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'skip_download': False,
        'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'writethumbnail': True,
    }

    try:
        queue.put(json.dumps({
            'type': 'log',
            'message': f'[{song_index}/{total_songs}] Searching for "{song_name}"...'
        }))
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song_name, download=True)
        
        title = sanitize_filename(info.get("title", song_name))
        artist = info.get("artist") or info.get("channel") or info.get("uploader") or "Unknown Artist"
        album = info.get("album") or "YouTube"
        thumbnail_url = info.get("thumbnail")
        duration = info.get("duration", 0)

        mp3_path = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{title}.mp3")

        # Embed metadata + thumbnail
        if os.path.exists(mp3_path):
            try:
                audio = EasyID3(mp3_path)
            except:
                audio = EasyID3()
            audio["title"] = title
            audio["artist"] = artist
            audio["album"] = album
            audio.save(mp3_path)

            if thumbnail_url:
                try:
                    img_data = requests.get(thumbnail_url, timeout=10).content
                    audio = ID3(mp3_path)
                    audio['APIC'] = APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Cover',
                        data=img_data
                    )
                    audio.save(mp3_path)
                except Exception as img_err:
                    queue.put(json.dumps({
                        'type': 'log',
                        'message': f'Warning: Could not embed thumbnail for {title}'
                    }))

        return {
            'success': True,
            'title': title,
            'artist': artist,
            'album': album,
            'thumbnail': thumbnail_url,
            'duration': duration,
            'filename': f"{title}.mp3",
            'download_url': f"/download_file/{title}.mp3"
        }

    except Exception as e:
        queue.put(json.dumps({
            'type': 'log',
            'message': f'Error downloading "{song_name}": {str(e)}'
        }))
        return {
            'success': False,
            'song_name': song_name,
            'error': str(e)
        }

def batch_download(songs, queue, online_mode=False):
    """Download multiple songs and report progress."""
    total = len(songs)
    results = []
    
    queue.put(json.dumps({
        'type': 'batch_start',
        'total_songs': total,
        'songs': songs,
        'online_mode': online_mode
    }))
    
    for i, song in enumerate(songs, 1):
        result = search_and_download_youtube(song, queue, song_index=i, total_songs=total, online_mode=online_mode)
        results.append(result)
        
        if result['success']:
            queue.put(json.dumps({
                'type': 'song_completed',
                'song_index': i,
                'total_songs': total,
                'title': result['title'],
                'artist': result['artist'],
                'album': result['album'],
                'thumbnail': result.get('thumbnail', ''),
                'filename': result['filename'],
                'download_url': result.get('download_url', ''),
                'online_mode': online_mode
            }))
        else:
            queue.put(json.dumps({
                'type': 'song_error',
                'song_index': i,
                'total_songs': total,
                'song_name': result['song_name'],
                'error': result['error']
            }))
    
    # Final completion message
    successful = sum(1 for r in results if r['success'])
    queue.put(json.dumps({
        'type': 'completed',
        'total_songs': total,
        'successful': successful,
        'failed': total - successful,
        'results': results,
        'online_mode': online_mode
    }))

@app.route('/')
def index():
    return render_template('index.html', on_host=ON_HOST)

@app.route('/download', methods=['POST'])
def download():
    song_input = request.form['song_name']
    online_mode = request.form.get('online_mode', 'false') == 'true'
    songs = parse_batch_songs(song_input)
    
    if not songs:
        return render_template('download.html', song_name="No songs specified", songs=[], is_batch=False)
    
    # Create a unique queue for this download session
    import uuid
    session_id = str(uuid.uuid4())
    queue = Queue()
    progress_queues[session_id] = queue
    
    is_batch = len(songs) > 1
    
    download_thread = threading.Thread(target=batch_download, args=(songs, queue, online_mode))
    download_thread.start()
    
    return render_template('download.html', 
                          song_name=song_input, 
                          songs=songs, 
                          is_batch=is_batch,
                          session_id=session_id,
                          online_mode=online_mode)

@app.route('/progress/<session_id>')
def progress(session_id):
    def generate():
        queue = progress_queues.get(session_id)
        if not queue:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid session'})}\n\n"
            return
        
        while True:
            try:
                message = queue.get(timeout=60)  # 60 second timeout
                yield f"data: {message}\n\n"
                data = json.loads(message)
                if data.get('type') in ['completed', 'error']:
                    # Cleanup queue after completion
                    if session_id in progress_queues:
                        del progress_queues[session_id]
                    break
            except:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Timeout waiting for progress'})}\n\n"
                break
    
    return Response(generate(), mimetype='text/event-stream')

# Keep old progress endpoint for backward compatibility
@app.route('/progress')
def progress_old():
    return Response("data: {\"type\": \"error\", \"message\": \"Use session-based progress endpoint\"}\n\n", 
                   mimetype='text/event-stream')

# ========================================
# YOUTUBE TRENDING SONGS (ON_HOST MODE)
# ========================================

# Cache for trending songs to avoid excessive API calls
trending_cache = {
    'songs': [],
    'timestamp': 0,
    'ttl': 3600  # 1 hour cache
}

def fetch_trending_songs(limit=50):
    """Fetch trending/popular songs from YouTube Music charts."""
    current_time = time.time()
    
    # Return cached if valid
    if trending_cache['songs'] and (current_time - trending_cache['timestamp']) < trending_cache['ttl']:
        return trending_cache['songs'][:limit]
    
    try:
        # Search for current trending/popular music
        search_queries = [
            'top hits 2025 music',
            'trending songs 2025',
            'popular music today',
            'viral hits 2025',
            'top 50 songs this week'
        ]
        
        all_songs = []
        seen_ids = set()
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
        }
        
        for query in search_queries:
            if len(all_songs) >= limit:
                break
                
            try:
                search_url = f'ytsearch20:{query}'
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    results = ydl.extract_info(search_url, download=False)
                
                entries = results.get('entries', []) if results else []
                
                for entry in entries:
                    if entry and entry.get('id') not in seen_ids:
                        video_id = entry.get('id', '')
                        duration_secs = entry.get('duration', 0) or 0
                        
                        # Skip very long videos (likely not songs)
                        if duration_secs > 600:  # > 10 minutes
                            continue
                        
                        mins = int(duration_secs // 60)
                        secs = int(duration_secs % 60)
                        duration_str = f"{mins}:{secs:02d}"
                        
                        song = {
                            'id': video_id,
                            'title': entry.get('title', 'Unknown'),
                            'artist': entry.get('channel', entry.get('uploader', 'Unknown Artist')),
                            'duration': duration_str,
                            'duration_secs': duration_secs,
                            'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg" if video_id else None,
                            'is_trending': True
                        }
                        all_songs.append(song)
                        seen_ids.add(video_id)
                        
                        if len(all_songs) >= limit:
                            break
            except Exception as e:
                print(f"Error fetching trending for '{query}': {e}")
                continue
        
        # Update cache
        if all_songs:
            trending_cache['songs'] = all_songs
            trending_cache['timestamp'] = current_time
        
        return all_songs[:limit]
    
    except Exception as e:
        print(f"Error fetching trending songs: {e}")
        return []

@app.route('/api/trending')
def get_trending():
    """API endpoint to get trending songs."""
    limit = request.args.get('limit', 30, type=int)
    songs = fetch_trending_songs(limit)
    return jsonify({
        'songs': songs,
        'on_host': ON_HOST,
        'demo_duration': DEMO_PLAY_DURATION if ON_HOST else None
    })

@app.route('/api/config')
def get_config():
    """Get app configuration for frontend."""
    return jsonify({
        'on_host': ON_HOST,
        'demo_play_duration': DEMO_PLAY_DURATION if ON_HOST else None,
        'version': '2.0.0'
    })

@app.route('/songs')
def list_songs():
    if ON_HOST:
        # In ON_HOST mode, show trending songs instead of local library
        trending = fetch_trending_songs(30)
        return render_template('songs.html', 
                             songs=[], 
                             trending_songs=trending,
                             on_host=True,
                             demo_duration=DEMO_PLAY_DURATION)
    else:
        # Local mode - show local library
        songs = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith('.mp3')]
        return render_template('songs.html', 
                             songs=songs, 
                             trending_songs=[],
                             on_host=False,
                             demo_duration=None)

@app.route('/play/<filename>')
def play(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename)

@app.route('/download_file/<filename>')
def download_file(filename):
    """Serve file for direct browser download (online mode)."""
    return send_from_directory(
        app.config['DOWNLOAD_FOLDER'], 
        filename, 
        as_attachment=True,
        download_name=filename
    )


def get_cached_artwork(filename, folder):
    """Get artwork path with caching to improve performance."""
    cache_key = filename
    current_time = time.time()
    
    # Check cache
    if cache_key in artwork_cache:
        cached_path, cached_time = artwork_cache[cache_key]
        if current_time - cached_time < ARTWORK_CACHE_TTL:
            return cached_path
    
    # Find artwork and cache result
    result = find_matching_artwork(filename, folder)
    artwork_cache[cache_key] = (result, current_time)
    return result


def find_matching_artwork(filename, folder):
    """
    Search for artwork images in the music folder that match the song name.
    Looks for common patterns like: song_name.jpg, cover.jpg, folder.jpg, album art, etc.
    """
    if not filename:
        return None
    
    # Get the base name without extension
    base_name = os.path.splitext(filename)[0].lower()
    
    # Extract keywords from the filename (split by common separators)
    keywords = re.split(r'[\s\-_\.\(\)\[\]]+', base_name)
    keywords = [k.strip() for k in keywords if k.strip() and len(k) > 2]
    
    # Common image extensions
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
    
    # Common cover art filenames to check first (highest priority)
    common_covers = ['cover', 'folder', 'album', 'artwork', 'front', 'albumart', 'albumartsmall']
    
    try:
        # Get all files in the directory
        all_files = os.listdir(folder)
        image_files = [f for f in all_files if f.lower().endswith(image_extensions)]
        
        if not image_files:
            return None
        
        # Priority 1: Exact match with song name (e.g., "song_name.jpg")
        for img in image_files:
            img_base = os.path.splitext(img)[0].lower()
            if img_base == base_name:
                return os.path.join(folder, img)
        
        # Priority 2: Song name starts with image name or vice versa
        for img in image_files:
            img_base = os.path.splitext(img)[0].lower()
            if base_name.startswith(img_base) or img_base.startswith(base_name):
                return os.path.join(folder, img)
        
        # Priority 3: Common cover filenames (cover.jpg, folder.jpg, etc.)
        for cover_name in common_covers:
            for img in image_files:
                img_base = os.path.splitext(img)[0].lower()
                if img_base == cover_name or cover_name in img_base:
                    return os.path.join(folder, img)
        
        # Priority 4: Keyword matching - find images that share keywords with the song
        best_match = None
        best_score = 0
        
        for img in image_files:
            img_base = os.path.splitext(img)[0].lower()
            img_keywords = re.split(r'[\s\-_\.\(\)\[\]]+', img_base)
            img_keywords = [k.strip() for k in img_keywords if k.strip() and len(k) > 2]
            
            # Calculate match score
            score = 0
            for keyword in keywords:
                for img_kw in img_keywords:
                    if keyword == img_kw:
                        score += 3  # Exact keyword match
                    elif keyword in img_kw or img_kw in keyword:
                        score += 1  # Partial match
            
            if score > best_score:
                best_score = score
                best_match = os.path.join(folder, img)
        
        # Only return if we have a reasonable match (at least 2 points)
        if best_score >= 2:
            return best_match
        
        # Priority 5: If there's only one image in the folder, use it as a fallback
        if len(image_files) == 1:
            return os.path.join(folder, image_files[0])
        
    except Exception as e:
        print(f"Error searching for artwork: {e}")
    
    return None


@app.route('/cover/<path:filename>')
def cover(filename):
    # Serve embedded cover art from MP3 APIC frame when available
    file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return send_from_directory('static', 'default-artwork.png')
    try:
        tags = ID3(file_path)
        apic = None
        for key in tags.keys():
            if key.startswith('APIC'):
                apic = tags.get(key)
                break
        if apic and getattr(apic, 'data', None):
            mime = getattr(apic, 'mime', 'image/jpeg') or 'image/jpeg'
            return send_file(io.BytesIO(apic.data), mimetype=mime)
    except Exception:
        pass
    
    # No embedded cover - search for matching artwork in music directory (with caching)
    matching_art = get_cached_artwork(filename, app.config['DOWNLOAD_FOLDER'])
    if matching_art and os.path.exists(matching_art):
        return send_file(matching_art)
    
    return send_from_directory('static', 'default-artwork.png')


# ========================================
# RECOMMENDATION API ENDPOINTS
# ========================================

@app.route('/api/recommend/record', methods=['POST'])
def record_play_event():
    """Record a play event for learning."""
    try:
        data = request.get_json()
        song_name = data.get('song_name')
        completed = data.get('completed', True)
        duration_played = data.get('duration_played', 0)
        total_duration = data.get('total_duration', 0)
        skipped = data.get('skipped', False)
        
        if not song_name:
            return jsonify({'error': 'song_name required'}), 400
        
        result = recommendation_engine.record_play(
            song_name, completed, duration_played, total_duration, skipped
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommend/score/<path:song_name>')
def get_song_score(song_name):
    """Get the preference score for a specific song."""
    try:
        score_data = recommendation_engine.calculate_song_score(song_name)
        return jsonify(score_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommend/shuffle')
def get_smart_shuffle():
    """Get smart shuffle order for all songs."""
    try:
        songs = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith('.mp3')]
        shuffle_order = recommendation_engine.get_smart_shuffle_order(songs)
        return jsonify({
            'order': [s['name'] for s in shuffle_order],
            'scores': [{
                'name': s['name'],
                'score': round(s['score'], 3)
            } for s in shuffle_order]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommend/download-suggestions')
def get_download_suggestions():
    """Get download recommendations based on learned preferences."""
    try:
        count = request.args.get('count', 5, type=int)
        recommendations = recommendation_engine.get_download_recommendations(count)
        return jsonify({'recommendations': recommendations})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommend/preferences')
def get_preferences_summary():
    """Get a summary of learned preferences."""
    try:
        summary = recommendation_engine.get_preference_summary()
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommend/reset', methods=['POST'])
def reset_preferences():
    """Reset all learned preferences."""
    try:
        recommendation_engine.reset_preferences()
        return jsonify({'success': True, 'message': 'Preferences reset successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ========================================
# STREAMING API ENDPOINTS
# ========================================

@app.route('/api/stream/search')
def stream_search():
    """Search YouTube for songs without downloading - returns streamable results."""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 10, type=int)
    
    if not query:
        return jsonify({'error': 'Query required'}), 400
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
        }
        
        # Use search URL format instead of default_search
        search_url = f'ytsearch{limit}:{query}'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(search_url, download=False)
        
        songs = []
        entries = results.get('entries', []) if results else []
        
        for entry in entries[:limit]:
            if entry:
                video_id = entry.get('id', '')
                duration_secs = entry.get('duration', 0) or 0
                # Format duration as mm:ss
                mins = int(duration_secs // 60)
                secs = int(duration_secs % 60)
                duration_str = f"{mins}:{secs:02d}"
                
                songs.append({
                    'id': video_id,
                    'title': entry.get('title', 'Unknown'),
                    'channel': entry.get('channel', entry.get('uploader', 'Unknown Artist')),
                    'duration': duration_str,
                    'duration_secs': duration_secs,
                    'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg" if video_id else None,
                    'url': entry.get('url', ''),
                    'view_count': entry.get('view_count', 0),
                })
        
        return jsonify({'results': songs, 'query': query})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stream/url/<video_id>')
def get_stream_url(video_id):
    """Get direct audio stream URL for a YouTube video."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'bestaudio/best',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
        
        # Get the best audio format URL
        formats = info.get('formats', [])
        audio_url = None
        
        # Prefer audio-only formats
        for f in formats:
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                audio_url = f.get('url')
                break
        
        # Fallback to best format
        if not audio_url:
            audio_url = info.get('url') or (formats[-1].get('url') if formats else None)
        
        return jsonify({
            'stream_url': audio_url,
            'title': info.get('title', 'Unknown'),
            'artist': info.get('channel', info.get('uploader', 'Unknown Artist')),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"),
            'video_id': video_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stream/video/<video_id>')
def get_video_stream_url(video_id):
    """Get video info and proxy URL for a YouTube video (for custom player)."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best[height<=720][ext=mp4]/best[height<=720]/best',  # Prefer 720p mp4 for compatibility
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
        
        # Use our proxy URL instead of direct YouTube URL (to avoid CORS)
        proxy_url = f'/api/stream/video-proxy/{video_id}'
        
        return jsonify({
            'video_url': proxy_url,
            'title': info.get('title', 'Unknown'),
            'channel': info.get('channel', info.get('uploader', 'Unknown Artist')),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"),
            'video_id': video_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Video stream cache to avoid repeated yt-dlp calls
video_stream_cache = {}
VIDEO_CACHE_TTL = 3600  # 1 hour

@app.route('/api/stream/video-proxy/<video_id>')
def video_proxy(video_id):
    """Proxy video stream to avoid CORS issues."""
    try:
        # Check cache
        cache_key = f"video_{video_id}"
        now = time.time()
        
        if cache_key in video_stream_cache:
            cached = video_stream_cache[cache_key]
            if now - cached['timestamp'] < VIDEO_CACHE_TTL:
                video_url = cached['url']
            else:
                del video_stream_cache[cache_key]
                video_url = None
        else:
            video_url = None
        
        # Fetch new URL if not cached
        if not video_url:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'format': 'best[height<=720][ext=mp4]/best[height<=720]/best',
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
            
            video_url = info.get('url')
            
            if not video_url:
                formats = info.get('formats', [])
                for f in reversed(formats):
                    if f.get('ext') == 'mp4' and f.get('acodec') != 'none' and f.get('vcodec') != 'none':
                        height = f.get('height', 0) or 0
                        if height <= 720:
                            video_url = f.get('url')
                            break
                
                if not video_url and formats:
                    for f in reversed(formats):
                        if f.get('acodec') != 'none' and f.get('vcodec') != 'none':
                            video_url = f.get('url')
                            break
            
            # Cache the URL
            if video_url:
                video_stream_cache[cache_key] = {
                    'url': video_url,
                    'timestamp': now
                }
        
        if not video_url:
            return jsonify({'error': 'Could not get video URL'}), 404
        
        # Get range header for seeking support
        range_header = request.headers.get('Range')
        headers = {}
        if range_header:
            headers['Range'] = range_header
        
        # Stream the video through our server
        resp = requests.get(video_url, headers=headers, stream=True)
        
        # Build response headers
        response_headers = {
            'Content-Type': resp.headers.get('Content-Type', 'video/mp4'),
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*',
        }
        
        if 'Content-Length' in resp.headers:
            response_headers['Content-Length'] = resp.headers['Content-Length']
        if 'Content-Range' in resp.headers:
            response_headers['Content-Range'] = resp.headers['Content-Range']
        
        def generate():
            for chunk in resp.iter_content(chunk_size=8192):
                yield chunk
        
        status_code = resp.status_code
        return Response(generate(), status=status_code, headers=response_headers)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stream/similar/<video_id>')
def get_similar_songs(video_id):
    """Get similar/related songs for a given video - like YouTube Music's 'Up Next'."""
    limit = request.args.get('limit', 10, type=int)
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        
        # Get video info including related videos
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
        
        # Try to get related videos or use search based on title
        title = info.get('title', '')
        artist = info.get('channel', info.get('uploader', ''))
        
        # Search for similar songs based on title and artist
        search_queries = []
        if artist:
            search_queries.append(f"{artist} songs")
        if title:
            # Extract potential genre/mood keywords
            keywords = re.split(r'[\s\-_\(\)\[\]]+', title.lower())
            keywords = [k for k in keywords if len(k) > 3][:3]
            if keywords:
                search_queries.append(' '.join(keywords) + ' music')
        
        similar_songs = []
        seen_ids = {video_id}  # Don't include the current song
        
        for search_q in search_queries[:2]:
            if len(similar_songs) >= limit:
                break
            
            search_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
            }
            
            # Use search URL format instead of default_search
            search_url = f'ytsearch{limit}:{search_q}'
            
            with yt_dlp.YoutubeDL(search_opts) as ydl:
                results = ydl.extract_info(search_url, download=False)
            
            entries = results.get('entries', []) if results else []
            for entry in entries:
                if entry and entry.get('id') not in seen_ids:
                    vid = entry.get('id', '')
                    duration_secs = entry.get('duration', 0) or 0
                    mins = int(duration_secs // 60)
                    secs = int(duration_secs % 60)
                    duration_str = f"{mins}:{secs:02d}"
                    
                    similar_songs.append({
                        'id': vid,
                        'title': entry.get('title', 'Unknown'),
                        'channel': entry.get('channel', entry.get('uploader', 'Unknown Artist')),
                        'duration': duration_str,
                        'thumbnail': f"https://img.youtube.com/vi/{vid}/mqdefault.jpg" if vid else None,
                    })
                    seen_ids.add(vid)
                    
                    if len(similar_songs) >= limit:
                        break
        
        return jsonify({
            'similar': similar_songs[:limit],
            'based_on': {
                'id': video_id,
                'title': title,
                'artist': artist
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stream/download', methods=['POST'])
def stream_download():
    """Download a song from streaming (save to library)."""
    try:
        data = request.get_json()
        video_id = data.get('video_id')
        
        if not video_id:
            return jsonify({'error': 'video_id required'}), 400
        
        url = f'https://www.youtube.com/watch?v={video_id}'
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        
        title = sanitize_filename(info.get('title', 'Unknown'))
        filename = f"{title}.mp3"
        
        # Try to add metadata
        mp3_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        if os.path.exists(mp3_path):
            try:
                audio = EasyID3(mp3_path)
                audio["title"] = title
                audio["artist"] = info.get('channel', info.get('uploader', 'Unknown Artist'))
                audio.save()
                
                # Try to embed thumbnail
                thumbnail_url = info.get('thumbnail')
                if thumbnail_url:
                    img_data = requests.get(thumbnail_url, timeout=10).content
                    audio = ID3(mp3_path)
                    audio['APIC'] = APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Cover',
                        data=img_data
                    )
                    audio.save()
            except Exception as e:
                print(f"Could not add metadata: {e}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'title': title
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get radio state
@app.route('/api/radio/state')
def get_radio_state():
    return json.dumps({
        'is_live': radio_state['is_live'],
        'listeners': radio_state['listeners'],
        'track_info': radio_state['track_info'],
        'is_playing': radio_state['is_playing']
    })

# SocketIO Events for Live Radio
@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')
    # Send current radio state to newly connected client
    emit('radio_state', {
        'is_live': radio_state['is_live'],
        'listeners': radio_state['listeners'],
        'track_info': radio_state['track_info'],
        'is_playing': radio_state['is_playing'],
        'current_time': radio_state['current_time']
    })

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')
    # If host disconnects, end the radio
    if radio_state['host_sid'] == request.sid:
        radio_state['is_live'] = False
        radio_state['host_sid'] = None
        radio_state['listeners'] = 0
        socketio.emit('radio_ended', {'message': 'Host ended the radio'})
    elif radio_state['is_live']:
        radio_state['listeners'] = max(0, radio_state['listeners'] - 1)
        socketio.emit('listener_update', {'listeners': radio_state['listeners']})

@socketio.on('start_radio')
def handle_start_radio(data):
    """Host starts the radio broadcast"""
    # Check if request is from localhost (host)
    client_ip = request.remote_addr
    if client_ip not in ['127.0.0.1', 'localhost', '::1']:
        emit('error', {'message': 'Only the host can start the radio'})
        return
    
    radio_state['is_live'] = True
    radio_state['host_sid'] = request.sid
    radio_state['listeners'] = 0
    radio_state['current_track'] = data.get('track')
    radio_state['current_time'] = data.get('current_time', 0)
    radio_state['is_playing'] = data.get('is_playing', False)
    radio_state['track_info'] = {
        'title': data.get('title', 'Unknown'),
        'artist': data.get('artist', 'Unknown Artist'),
        'cover': data.get('cover', '')
    }
    
    # Broadcast to all clients that radio is live
    socketio.emit('radio_started', {
        'track_info': radio_state['track_info'],
        'current_time': radio_state['current_time'],
        'is_playing': radio_state['is_playing'],
        'track': radio_state['current_track']
    })
    print(f'Radio started by host: {request.sid}')

@socketio.on('stop_radio')
def handle_stop_radio():
    """Host stops the radio broadcast"""
    if radio_state['host_sid'] != request.sid:
        emit('error', {'message': 'Only the host can stop the radio'})
        return
    
    radio_state['is_live'] = False
    radio_state['host_sid'] = None
    radio_state['listeners'] = 0
    
    socketio.emit('radio_ended', {'message': 'Radio broadcast ended'})
    print('Radio stopped')

@socketio.on('join_radio')
def handle_join_radio():
    """Listener joins the radio"""
    if not radio_state['is_live']:
        emit('error', {'message': 'Radio is not live'})
        return
    
    radio_state['listeners'] += 1
    join_room('radio_listeners')
    
    # Send current state to the new listener
    emit('sync_playback', {
        'track': radio_state['current_track'],
        'current_time': radio_state['current_time'],
        'is_playing': radio_state['is_playing'],
        'track_info': radio_state['track_info']
    })
    
    # Broadcast updated listener count
    socketio.emit('listener_update', {'listeners': radio_state['listeners']})
    print(f'Listener joined. Total: {radio_state["listeners"]}')

@socketio.on('leave_radio')
def handle_leave_radio():
    """Listener leaves the radio"""
    if radio_state['is_live']:
        radio_state['listeners'] = max(0, radio_state['listeners'] - 1)
        leave_room('radio_listeners')
        socketio.emit('listener_update', {'listeners': radio_state['listeners']})

@socketio.on('host_sync')
def handle_host_sync(data):
    """Host broadcasts current playback state"""
    if radio_state['host_sid'] != request.sid:
        return
    
    radio_state['current_time'] = data.get('current_time', 0)
    radio_state['is_playing'] = data.get('is_playing', False)
    
    if data.get('track'):
        radio_state['current_track'] = data['track']
    if data.get('track_info'):
        radio_state['track_info'] = data['track_info']
    
    # Broadcast to all listeners
    socketio.emit('sync_playback', {
        'track': radio_state['current_track'],
        'current_time': radio_state['current_time'],
        'is_playing': radio_state['is_playing'],
        'track_info': radio_state['track_info']
    }, room='radio_listeners')

@socketio.on('host_track_change')
def handle_host_track_change(data):
    """Host changes the track"""
    if radio_state['host_sid'] != request.sid:
        return
    
    radio_state['current_track'] = data.get('track')
    radio_state['current_time'] = 0
    radio_state['is_playing'] = data.get('is_playing', True)
    radio_state['track_info'] = {
        'title': data.get('title', 'Unknown'),
        'artist': data.get('artist', 'Unknown Artist'),
        'cover': data.get('cover', '')
    }
    
    # Broadcast track change to all listeners
    socketio.emit('track_changed', {
        'track': radio_state['current_track'],
        'track_info': radio_state['track_info'],
        'is_playing': radio_state['is_playing']
    })

@socketio.on('host_play_pause')
def handle_host_play_pause(data):
    """Host plays or pauses"""
    if radio_state['host_sid'] != request.sid:
        return
    
    radio_state['is_playing'] = data.get('is_playing', False)
    radio_state['current_time'] = data.get('current_time', 0)
    
    socketio.emit('playback_state', {
        'is_playing': radio_state['is_playing'],
        'current_time': radio_state['current_time']
    })

@socketio.on('host_seek')
def handle_host_seek(data):
    """Host seeks to position"""
    if radio_state['host_sid'] != request.sid:
        return
    
    radio_state['current_time'] = data.get('current_time', 0)
    
    socketio.emit('seek_to', {
        'current_time': radio_state['current_time']
    })

if __name__ == '__main__':
    socketio.run(
    app,
    host='0.0.0.0',
    port=5000,
    debug=True,
    allow_unsafe_werkzeug=True)
