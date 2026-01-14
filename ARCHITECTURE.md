# Architecture: Unified Favorites and Smart Recommendations

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         MUSIFY PLAYER                            │
│                                                                   │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │  Local Library   │              │  Streaming/YT    │         │
│  │   (Offline)      │              │    (Online)      │         │
│  └────────┬─────────┘              └────────┬─────────┘         │
│           │                                  │                    │
│           └──────────┬──────────────────────┘                    │
│                      │                                            │
│           ┌──────────▼──────────┐                                │
│           │  UNIFIED FAVORITES  │                                │
│           │    SYSTEM (NEW)     │                                │
│           └──────────┬──────────┘                                │
│                      │                                            │
│                      ▼                                            │
│           ┌─────────────────────┐                                │
│           │  Recommendation     │                                │
│           │  Engine (Enhanced)  │                                │
│           └──────────┬──────────┘                                │
│                      │                                            │
│         ┌────────────┴────────────┐                              │
│         │                         │                               │
│         ▼                         ▼                               │
│  ┌─────────────┐          ┌──────────────┐                      │
│  │Smart Shuffle│          │  AI-Sorted   │                      │
│  │  (Library)  │          │  Up Next     │                      │
│  └─────────────┘          └──────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Offline Playback Flow
```
User Plays Local Song
    ↓
Record Play Event → Recommendation Engine
    ↓
Update Preference Data (keywords, artists, genres)
    ↓
Next Track Selection:
    ├─ If Shuffle: Smart Shuffle Order
    │   └─ get_smart_shuffle_order(songs, type='local')
    │       └─ Returns songs sorted by learned preferences
    └─ If Sequential: Next in library
```

### 2. Streaming Playback Flow
```
User Plays Streaming Song
    ↓
Store Song Metadata (id, title, artist, thumbnail)
    ↓
Record Play Event → Recommendation Engine
    ↓
Load Similar Songs:
    ├─ Fetch from YouTube API (limit + SMART_ORDER_BUFFER)
    ├─ Score each song: calculate_streaming_song_score()
    └─ Order by AI: get_smart_shuffle_order(songs, type='streaming')
        └─ Returns AI-sorted upnext queue
    ↓
Display with "AI SORTED" badge
    ↓
Next Track: Pop from streaming queue
```

### 3. Favorites System Flow
```
User Clicks Like Button
    ↓
Check Current Mode:
    ├─ Offline Mode:
    │   └─ Add to likedTracks[] (filename)
    │       └─ localStorage.setItem('likedTracks')
    │
    └─ Streaming Mode:
        └─ Add to likedStreamingSongs[] (full metadata)
            └─ localStorage.setItem('likedStreamingSongs')
                └─ Stores: {id, title, artist, thumbnail, liked_at}
```

## API Architecture

### Backend Endpoints

```
┌─────────────────────────────────────────────────────────┐
│                    Flask Backend (app.py)                │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  GET /songs                                              │
│    └─ Returns: local_songs[] + trending_songs[]         │
│                                                           │
│  GET /api/favorites/list                                 │
│    └─ Returns: enriched favorites with scores           │
│                                                           │
│  POST /api/recommend/suggestions                         │
│    ├─ mode: 'offline' → local smart shuffle             │
│    └─ mode: 'streaming' → context for YouTube           │
│                                                           │
│  GET /api/stream/similar/<video_id>?smart=true          │
│    ├─ Fetch songs from YouTube                          │
│    ├─ Score with recommendation engine                   │
│    └─ Return AI-sorted results                          │
│                                                           │
│  GET /api/recommend/shuffle                              │
│    └─ Smart shuffle for local library                   │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Recommendation Engine Architecture

```
┌─────────────────────────────────────────────────────────┐
│           MusicRecommendationEngine (Enhanced)           │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Learned Data:                                           │
│    ├─ song_stats: {play_count, skip_count, completion}  │
│    ├─ keyword_scores: {word: preference_score}          │
│    ├─ artist_scores: {artist: preference_score}         │
│    ├─ genre_hints: {genre: preference_score}            │
│    └─ time_preferences: {hour: {keywords}}              │
│                                                           │
│  Methods:                                                │
│    ├─ record_play(song, completed, skipped)             │
│    │   └─ Updates all preference data                   │
│    │                                                      │
│    ├─ calculate_song_score(filename)                    │
│    │   └─ Scores local library song                     │
│    │                                                      │
│    ├─ calculate_streaming_song_score(title, artist)     │
│    │   └─ Scores streaming song (NEW)                   │
│    │                                                      │
│    └─ get_smart_shuffle_order(songs, type)              │
│        ├─ type='local': filename scoring                │
│        └─ type='streaming': metadata scoring (NEW)      │
│            └─ Returns AI-sorted list                    │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Separation of Concerns

### Streaming Mode
```
Current Song: YouTube Video
    ↓
Upnext Queue: Similar songs from YouTube API
    ↓
AI Sorting: Ordered by learned preferences
    ↓
Next Track: streamingQueue.shift()
    ↓
Uses: streamingAudio element (CORS-safe)
```

### Offline Mode
```
Current Song: Local MP3 file
    ↓
Upnext Queue: Library array
    ↓
Smart Shuffle: Ordered by learned preferences
    ↓
Next Track: From smart shuffled library
    ↓
Uses: audio element (with Wave Engine)
```

## Storage Architecture

### LocalStorage Structure
```javascript
{
  // Local favorites (backward compatible)
  likedTracks: ["song1.mp3", "song2.mp3", ...],
  
  // Streaming favorites (NEW)
  likedStreamingSongs: [
    {
      id: "video_id",
      title: "Song Title",
      artist: "Artist Name",
      thumbnail: "https://...",
      liked_at: "2025-01-14T10:00:00.000Z"
    },
    ...
  ],
  
  // Recommendation engine data
  musify_preferences: {
    song_stats: {...},
    keyword_scores: {...},
    artist_scores: {...},
    genre_hints: {...},
    time_preferences: {...}
  },
  
  // UI preferences
  musify_streaming_mode: "true|false",
  musify_view_mode: "list|grid|compact"
}
```

## Key Design Decisions

### 1. Separate Audio Elements
- **Local**: `audio` element (supports Wave Engine)
- **Streaming**: `streamingAudio` element (avoids CORS)

### 2. Separate Queues
- **Local**: Library array with smart shuffle
- **Streaming**: YouTube upnext queue

### 3. Unified Scoring
- Same recommendation engine
- Different input formats (filename vs metadata)
- Consistent output (score + features)

### 4. Metadata Storage
- **Local favorites**: Filename only (lightweight)
- **Streaming favorites**: Full metadata (for display)

### 5. AI Sorting
- Fetch extra songs (SMART_ORDER_BUFFER = 10)
- Score all candidates
- Return top N sorted by preference
- Visual indicator ("AI SORTED" badge)

## Performance Considerations

1. **Caching**: Trending songs cached for 1 hour
2. **Lazy Loading**: Only fetch similar songs when needed
3. **Buffer Optimization**: Fetch limit + 10 instead of 2x
4. **Error Handling**: Graceful degradation on failures
5. **LocalStorage**: Efficient JSON serialization

## Future Enhancement Opportunities

1. Cross-mode recommendations
2. Unified search across all favorites
3. Playlist creation with mixed content
4. Export/import favorites
5. Cloud sync for favorites
6. More sophisticated AI models
7. User preference dashboard

## Backward Compatibility

✅ Existing `likedTracks` preserved
✅ Existing recommendation data intact
✅ No breaking changes to API
✅ Graceful fallbacks for errors
✅ Progressive enhancement approach
