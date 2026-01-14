# Implementation Notes: Unified Favorites and Enhanced Song Suggestions

## Overview
This implementation enhances the Musify music player to support unified favorites across both offline (local library) and streaming (YouTube) songs, with an improved song suggestion algorithm that works seamlessly for both modes.

## Key Changes

### 1. Backend Changes (app.py)

#### Modified Routes
- **`/songs` route**: Now returns both local library songs AND trending songs without discrimination
  - Previously: Showed either local OR trending based on ON_HOST mode
  - Now: Returns both, allowing the frontend to display all songs

#### New API Endpoints

##### `/api/favorites/list` (GET)
- Returns metadata about all favorite songs
- Provides enriched data for local songs with recommendation scores
- Response includes:
  - `local_songs`: Array of local library songs with scores
  - `on_host`: Boolean indicating host mode

##### `/api/recommend/suggestions` (POST)
- Smart song suggestions for both offline and streaming modes
- Request body:
  ```json
  {
    "mode": "offline|streaming",
    "current_song": "optional song name",
    "limit": 10
  }
  ```
- Response varies by mode:
  - **Offline mode**: Returns scored local songs using smart shuffle algorithm
  - **Streaming mode**: Returns context for YouTube API suggestions with learned preferences

#### Enhanced Recommendation Engine

##### New Method: `calculate_streaming_song_score(title, artist, video_id)`
- Calculates preference scores for streaming songs
- Uses title and artist to extract features and match against learned preferences
- Returns same score structure as local songs

##### Enhanced Method: `get_smart_shuffle_order(songs, song_type='local')`
- Now supports both 'local' and 'streaming' song types
- For streaming songs (dict format):
  - Extracts title, artist, id from dict
  - Calculates scores using streaming-specific logic
- For local songs (filename format):
  - Uses existing filename-based scoring
- Returns ordered list with scores and metadata

#### Enhanced `/api/stream/similar/<video_id>` Endpoint
- Added `smart` query parameter (default: true)
- When enabled:
  - Fetches 2x the requested songs
  - Applies recommendation engine scoring
  - Returns AI-sorted results
- Response includes:
  - `similar`: Array of similar songs
  - `smart_ordered`: Boolean indicating if AI sorting was applied
  - `based_on`: Context about the original video

### 2. Frontend Changes (templates/songs.html)

#### Enhanced Favorites System

##### New Variables
- `likedStreamingSongs`: Array stored in localStorage for streaming favorites
  ```javascript
  {
    id: "video_id",
    title: "Song Title",
    artist: "Artist Name",
    thumbnail: "thumbnail_url",
    liked_at: "ISO timestamp"
  }
  ```
- `currentStreamingSong`: Tracks currently playing streaming song for likes

##### Modified Functions

**`toggleLike()`**
- Now handles both streaming and local songs
- For streaming: Stores full metadata in `likedStreamingSongs`
- For local: Stores filename in `likedTracks`
- Seamlessly switches based on playback mode

**`updateLikeButtons()`**
- Checks like status for both streaming and local songs
- Updates UI based on current playback mode

#### Enhanced Streaming Features

**`playStreamingTrack(videoId, title, artist, thumbnail)`**
- Added artist and thumbnail parameters
- Stores complete song metadata in `currentStreamingSong`
- Updates like button state after loading
- Records play event for recommendation engine
- Shows "AI SORTED" badge on similar songs

**`loadSimilarSongs(videoId)`**
- Now uses smart ordering parameter
- Requests 20 songs for better AI sorting
- Passes `smart=true` to backend API

**`displaySimilarSongs(songs, smartOrdered)`**
- Shows "AI SORTED" badge when applicable
- Includes artist and thumbnail in data attributes
- Properly handles artist/channel field variations

### 3. How It Works

#### For Offline/Library Songs:
1. Songs are scored using the existing recommendation engine
2. Smart shuffle orders songs by learned preferences
3. Favorites stored in `likedTracks` (array of filenames)
4. Next song selected from library using shuffle/smart shuffle
5. Playback uses main audio element with Wave Engine support

#### For Streaming Songs:
1. Similar songs fetched from YouTube API
2. Recommendation engine scores each song based on title/artist
3. Songs reordered by AI preference scores
4. Favorites stored in `likedStreamingSongs` (array of objects with metadata)
5. Next song selected from streaming upnext queue
6. Playback uses separate streaming audio element (CORS-safe)

#### Proper Separation Maintained:
- **When streaming**: Next/autoplay uses `streamingQueue` (from YouTube similar API)
- **When offline**: Next/autoplay uses library array with smart shuffle
- Like/favorite system works independently for both
- No cross-contamination between modes

### 4. Benefits

1. **Unified Favorites**: Users can favorite both local and streaming songs
2. **Better Suggestions**: AI learns from all listening habits
3. **Smart Ordering**: Streaming upnext is personalized based on preferences
4. **No Discrimination**: All songs treated equally regardless of source
5. **Proper Separation**: Streaming and offline maintain separate queues
6. **Enhanced UX**: "AI SORTED" badge shows when smart ordering is active

### 5. Testing

All changes have been tested:
- ✅ Python syntax validation
- ✅ Flask app imports successfully
- ✅ New API endpoints registered
- ✅ Recommendation engine methods work correctly
- ✅ API endpoints return expected responses
- ✅ Smart shuffle handles both song types
- ✅ Streaming and local scoring work independently

### 6. Backward Compatibility

- Existing `likedTracks` localStorage preserved
- Existing recommendation data preserved
- Offline-only users: No changes to behavior
- Streaming-only users: Enhanced with AI sorting
- Mixed users: Best of both worlds

## Usage Examples

### Liking a Streaming Song
```javascript
// User plays a streaming song
playStreamingTrack('abc123', 'Shape of You', 'Ed Sheeran', 'thumbnail.jpg');

// User clicks like button
// Stores: { id: 'abc123', title: 'Shape of You', artist: 'Ed Sheeran', ... }
```

### Getting Smart Suggestions
```javascript
// For offline mode
fetch('/api/recommend/suggestions', {
  method: 'POST',
  body: JSON.stringify({ mode: 'offline', limit: 10 })
});

// For streaming mode
fetch('/api/recommend/suggestions', {
  method: 'POST',
  body: JSON.stringify({ 
    mode: 'streaming', 
    current_song: 'Currently Playing Song',
    limit: 10 
  })
});
```

### Loading AI-Sorted Similar Songs
```javascript
// Automatically uses smart ordering
const response = await fetch(`/api/stream/similar/${videoId}?smart=true&limit=20`);
const data = await response.json();
// data.smart_ordered = true
// data.similar = [sorted songs with scores]
```

## Future Enhancements

Possible improvements:
1. Cross-mode recommendations (suggest streaming songs based on local listening)
2. Unified search across favorites from both sources
3. Playlist creation with mixed content
4. Export/import favorites
5. Sync favorites across devices
