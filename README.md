# NTS Radio → Spotify Playlist Creator

Automatically scrape tracklists from NTS Radio shows and create Spotify playlists with all discovered tracks.

## Features

- Scrapes complete tracklists from any NTS Radio show
- Searches and matches tracks on Spotify
- Creates organized playlists in your Spotify account
- Retry failed searches to improve match rates
- Progress tracking with colorful terminal output
- Saves all data locally in organised JSON files

## Prerequisites

- Python 3.7+
- Spotify Developer Account
- Active internet connection

## Installation

1. **Clone or download this repository**

2. **Install required packages:**
```bash
pip install -r requirements.txt
```

3. **Set up Spotify Developer Credentials:**
   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Create a new app
   - Note your `Client ID` and `Client Secret`
   - Add `http://localhost:8888/callback` to your app's Redirect URIs

4. **Create a `.env` file in the project directory:**
```env
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

## Usage

Run the script:
```bash
python nts_to_spotify.py
```

### Workflow

1. **Enter the NTS show alias** (e.g., `m00dtapes`, `charlie-bones`, `floating-points`)
   - You can find this in the URL: `https://www.nts.live/shows/m00dtapes`

2. **Choose an option from the menu:**

#### Option 1: Full Scrape and Search
- Fetches all episodes from the NTS show
- Extracts tracklists from each episode
- Searches for each track on Spotify
- Saves results to `data/{show_alias}/`

**Output files:**
- `tracklists_with_spotify.json` - Complete episode data with Spotify URIs
- `playlist_uris.json` - List of all matched Spotify track URIs

#### Option 2: Retry Failed Tracks
- Re-searches tracks that weren't found in Option 1
- Updates the JSON files with new matches
- Useful for improving match rates

#### Option 3: Create Spotify Playlist
- Authorizes with your Spotify account (browser popup)
- Creates a new private playlist in your library
- Adds all matched tracks to the playlist
- Returns a direct link to your new playlist

#### Option 4: Exit
- Closes the application

## File Structure

```
project/
├── main.py
├── .env
├── README.md
└── data/
    └── {show_alias}/
        ├── tracklists_with_spotify.json
        └── playlist_uris.json
```

## Example Output

```
NTS RADIO → SPOTIFY PLAYLIST CREATOR
============================================================

1. Full scrape and search (NTS → Spotify)
2. Retry failed tracks (search null spotify_uri)
3. Create Spotify playlist from URIs
4. Exit

============================================================

✓ Episodes processed: 48
✓ Total tracks: 672
✓ Tracks found on Spotify: 589
✓ Match rate: 87.6%

✓ Full data saved to: data/m00dtapes/tracklists_with_spotify.json
✓ Playlist URIs saved to: data/m00dtapes/playlist_uris.json
```

## Data Format

### tracklists_with_spotify.json
```json
[
  {
    "episode": "27th-november-2024",
    "broadcast": "2024-11-27T00:00:00Z",
    "url": "https://www.nts.live/shows/m00dtapes/episodes/27th-november-2024",
    "track_count": 15,
    "tracklist": [
      {
        "artist": "Artist Name",
        "title": "Track Title",
        "spotify_uri": "spotify:track:xxxxxxxxxxxxx",
        "found": true
      }
    ]
  }
]
```

### playlist_uris.json
```json
{
  "show_alias": "m00dtapes",
  "name": "M00DTAPES Collection",
  "description": "All tracks from m00dtapes shows on NTS Radio",
  "total_tracks": 589,
  "uris": [
    "spotify:track:xxxxxxxxxxxxx",
    "spotify:track:yyyyyyyyyyyyy"
  ]
}
```

## Troubleshooting

### "Authorization timeout"
- Make sure you click "Agree" in the browser popup within 2 minutes
- Check that port 8888 is not blocked by a firewall

### "Missing Spotify credentials"
- Verify your `.env` file exists in the same directory as the script
- Check that variable names match exactly: `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`

### Low match rates
- Run Option 2 to retry failed tracks
- Some tracks may not be available on Spotify
- Artist/title formatting differences can prevent matches

### "Error creating playlist"
- Make sure you completed the OAuth authorization (Option 3)
- Check your internet connection
- Verify your Spotify account is active

## Rate Limiting

The script includes built-in delays to respect API rate limits:
- NTS API: 0.3 seconds between requests
- Spotify API: 0.1 seconds between searches
- Parallel processing uses max 5 workers

## Notes

- The script uses multi-threading for faster episode processing
- All data is stored locally - no external database required
- Track matching is done by artist + title search (not always 100% accurate)

## License

MIT License - feel free to modify and distribute

## Contributing

Pull requests welcome! Areas for improvement:
- Better track matching algorithms
- Support for other radio stations
- Playlist deduplication
- Export to other music platforms

## Credits

Built with:
- [NTS Radio](https://www.nts.live/) - Audio streaming platform
- [Spotify Web API](https://developer.spotify.com/) - Music catalog
- Python 3 - Because it's awesome

---

**Enjoy your NTS playlists! 🎧**