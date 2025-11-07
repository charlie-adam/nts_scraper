# NTS Radio → Spotify Playlist Creator

Automatically scrape tracklists from NTS Radio shows and create Spotify playlists with all discovered tracks. Uses AI-powered matching to intelligently find the best Spotify matches for each track.

## Features

- Scrapes complete tracklists from any NTS Radio show
- **AI-powered track matching** using OpenAI to find the best Spotify matches
- **Interactive match confirmation** for uncertain matches
- Creates organized playlists in your Spotify account
- Retry failed searches to improve match rates
- Progress tracking with colorful terminal output
- Saves all data locally in organised JSON files

## Prerequisites

- Python 3.7+
- Spotify Developer Account
- OpenAI API Account
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

4. **Set up OpenAI API Key:**
   - Go to [OpenAI API Platform](https://platform.openai.com/api-keys)
   - Create a new API key
   - Note your API key

5. **Create a `.env` file in the project directory:**
```env
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
OPENAI_API_KEY=your_openai_api_key_here
```

## Usage

Run the script:
```bash
python main.py
```

### Workflow

1. **Enter the NTS show alias** (e.g., `m00dtapes`, `charlie-bones`, `floating-points`)
   - You can find this in the URL: `https://www.nts.live/shows/m00dtapes`

2. **Choose an option from the menu:**

#### Option 1: Full Scrape and Search
- Fetches all episodes from the NTS show
- Extracts tracklists from each episode
- Searches for each track on Spotify using AI-powered matching
- **Interactive confirmation** for uncertain matches (you'll be prompted to accept/reject)
- Saves results to `data/{show_alias}/`

**AI Matching Features:**
- Automatically accepts high-confidence matches (distance < 15.0)
- Prompts for confirmation on uncertain matches (distance 15.0-30.0)
- Automatically rejects poor matches (distance > 30.0)
- Understands that the same song can have different featured artists, subtitles, or remixes

**Output files:**
- `tracklists_with_spotify.json` - Complete episode data with Spotify URIs
- `playlist_uris.json` - List of all matched Spotify track URIs

#### Option 2: Retry Failed Tracks
- Re-searches tracks that weren't found in Option 1
- Uses AI to find better matches
- Updates the JSON files with new matches
- Useful for improving match rates

#### Option 3: Create Spotify Playlist
- Authorizes with your Spotify account (browser popup)
- Creates a new private playlist in your library
- Adds all matched tracks to the playlist
- Returns a direct link to your new playlist

#### Option 4: Exit
- Closes the application

## How AI Matching Works

The script uses OpenAI's GPT model to intelligently match tracks by understanding:

- **Same song with variations**: Matches tracks even when Spotify lists fewer featured artists, has different subtitles, or simplified titles
- **Classical music**: Recognizes different movements or parts of the same work
- **Remixes**: Only matches remixes when explicitly specified in the original
- **Rejections**: Avoids matching completely different songs, even if they're by the same artist or in a similar genre

Example matching decisions:
- ✓ `Pat Metheny - September Fifteenth (Dedicated To Bill Evans)` → `Pat Metheny - September Fifteenth`
- ✓ `Amaro Freitas ft. 5 artists - Mar De Cirandeiras` → `Amaro Freitas, Jeff Parker - Mar de Cirandeiras`
- ✗ `Charles Webster - Ready (Presence Radio Edit)` → `Synthetix - Ready For It` (different song)

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

[15/22]
Original: Big Bad Wolf / Sober - Blk Odyssy, Eimaral Sol
Spotify:  Bad Wolves - Sober
Distance: 16.0
Accept this match? (y/n/q to quit): n
✗ Rejected

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

### "Missing OpenAI API key"
- Verify your `.env` file exists in the same directory as the script
- Check that the variable name matches exactly: `OPENAI_API_KEY`
- Ensure your OpenAI account has available credits

### "Authorization timeout"
- Make sure you click "Agree" in the browser popup within 2 minutes
- Check that port 8888 is not blocked by a firewall

### "Missing Spotify credentials"
- Verify your `.env` file exists in the same directory as the script
- Check that variable names match exactly: `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`

### Low match rates
- Run Option 2 to retry failed tracks with AI matching
- Some tracks may not be available on Spotify
- Consider adjusting the distance threshold if too many matches require confirmation

### "Error creating playlist"
- Make sure you completed the OAuth authorization (Option 3)
- Check your internet connection
- Verify your Spotify account is active

## Rate Limiting

The script includes built-in delays to respect API rate limits:
- NTS API: 0.3 seconds between requests
- Spotify API: 0.1 seconds between searches
- OpenAI API: Included in request handling
- Parallel processing uses max 5 workers

## Configuration

You can adjust matching sensitivity by modifying the distance thresholds in the code:
- `< 15.0`: Auto-accept (high confidence)
- `15.0 - 30.0`: Requires confirmation
- `> 30.0`: Auto-reject (poor match)

## Notes

- The script uses multi-threading for faster episode processing
- All data is stored locally - no external database required
- AI-powered matching significantly improves accuracy over simple text search
- Interactive confirmation ensures you have control over uncertain matches

## License

MIT License - feel free to modify and distribute

## Contributing

Pull requests welcome! Areas for improvement:
- Fine-tune AI matching prompts
- Support for other radio stations
- Playlist deduplication
- Export to other music platforms
- Batch confirmation mode for power users

## Credits

Built with:
- [NTS Radio](https://www.nts.live/) - Audio streaming platform
- [Spotify Web API](https://developer.spotify.com/) - Music catalog
- [OpenAI API](https://openai.com/) - AI-powered track matching
- Python 3 - Because it's awesome

---

**Enjoy your NTS playlists!**