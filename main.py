import requests
import json
import time
import base64
import webbrowser
import urllib.parse
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Dict, Optional, List
from dotenv import load_dotenv
from tqdm import tqdm
from colorama import Fore, Style, init
from openai import OpenAI
# Initialize colorama for cross-platform color support
init(autoreset=True)

# Load environment variables
load_dotenv()

# Thread-safe lock for printing
print_lock = Lock()

def thread_safe_print(*args, **kwargs):
    """Thread-safe printing"""
    with print_lock:
        print(*args, **kwargs)

# Global variable to capture OAuth callback
auth_code = None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

SPOTIFY_SEARCH_MAX_WORKERS = 5

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def normalize_string(s: str) -> str:
    """Normalize string for comparison"""
    import re
    # Remove special characters, convert to lowercase, remove extra spaces
    s = re.sub(r'[^\w\s]', '', s.lower())
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def find_best_match(original_artist: str, original_title: str, tracks: List[Dict], threshold: int = 15) -> Optional[Dict]:
    """
    Find best match using AI, then backup Levenshtein distance, then backup manual confirmation.
    threshold: maximum edit distance to consider (default 15)
    """
    original_artist_norm = normalize_string(original_artist)
    original_title_norm = normalize_string(original_title)
    original_combined = f"{original_artist_norm} {original_title_norm}"
    
    best_match = None
    # If AI fails, fallback to Levenshtein distance

    prompt = f"Find the best match for: {original_artist} - {original_title} from the following options:\n"
    for i, track in enumerate(tracks, 1):
        spotify_artists = ", ".join([artist['name'] for artist in track.get('artists', [])])
        spotify_title = track.get('name', '')
        prompt += f"{i}. {spotify_artists} - {spotify_title}\n"
    
    prompt += "\nMatch if the candidate is clearly the SAME SONG/COMPOSITION, even if:\n"
    prompt += "- Spotify lists fewer featured artists/collaborators\n"
    prompt += "- Subtitles, dedications, or parenthetical info differ\n"
    prompt += "- It's a different movement/part of the same classical work\n"
    prompt += "- Track title is slightly simplified\n\n"
    
    prompt += "DO NOT match if:\n"
    prompt += "- It's a completely different song (even by same artist)\n"
    prompt += "- Only genre/mood is similar but different composition\n"
    prompt += "- Wrong remix version (unless original has no remix specified)\n\n"
    
    prompt += "Respond with ONLY the number of the match, or 0 if none match the same song."
    try:
        # print(f"{Fore.YELLOW}Using AI to find best match for: {original_artist} - {original_title}")
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that finds the best matching song from a list."},
                {"role": "user", "content": prompt}
            ],
            temperature=1
        )
        # print(response)
        answer = response.choices[0].message.content.strip()
        # print(f"{Fore.YELLOW}AI response: {answer}")
        choice = int(answer)
        if choice > 0 and choice <= len(tracks):
            selected_track = tracks[choice - 1]
            spotify_artists = ", ".join([artist['name'] for artist in selected_track.get('artists', [])])
            spotify_title = selected_track.get('name', '')
            # print(f"{Fore.GREEN}AI selected match: {spotify_artists} - {spotify_title} for {original_artist} - {original_title}")
            return {
                'uri': selected_track['uri'],
                'spotify_artist': spotify_artists,
                'spotify_title': spotify_title,
                'original_artist': original_artist,
                'original_title': original_title,
                'distance': 0,
                'needs_confirmation': False
            }
    except Exception as e:
        print(f"{Fore.RED}✗ AI matching failed with error: {e}")
        pass  # If AI fails, fallback to Levenshtein distance
    
    best_distance = float('inf')
    
    for track in tracks:
        # Get Spotify track info
        spotify_artists = ", ".join([artist['name'] for artist in track.get('artists', [])])
        spotify_title = track.get('name', '')
        
        spotify_artist_norm = normalize_string(spotify_artists)
        spotify_title_norm = normalize_string(spotify_title)
        spotify_combined = f"{spotify_artist_norm} {spotify_title_norm}"
        
        # Calculate distances
        combined_distance = levenshtein_distance(original_combined, spotify_combined)
        title_distance = levenshtein_distance(original_title_norm, spotify_title_norm)
        artist_distance = levenshtein_distance(original_artist_norm, spotify_artist_norm)
        
        # Weighted score (title is more important)
        weighted_distance = (title_distance * 2 + artist_distance) / 3
        
        if weighted_distance < best_distance:
            best_distance = weighted_distance
            best_match = {
                'uri': track['uri'],
                'spotify_artist': spotify_artists,
                'spotify_title': spotify_title,
                'original_artist': original_artist,
                'original_title': original_title,
                'distance': weighted_distance,
                'needs_confirmation': weighted_distance > threshold
            }
    
    # Only return if within reasonable threshold (even for confirmation)
    if best_match and best_match['distance'] <= threshold * 2:
        return best_match
    
    return None

def confirm_matches(pending_matches: List[Dict]) -> List[Dict]:
    """
    Show pending matches to user for confirmation.
    Returns list of confirmed matches.
    """
    if not pending_matches:
        return []
    
    print(f"\n{Fore.YELLOW}{'=' * 60}")
    print(f"{Fore.YELLOW}MATCHES REQUIRING CONFIRMATION: {len(pending_matches)}")
    print(f"{Fore.YELLOW}{'=' * 60}\n")
    
    confirmed = []
    
    for i, match in enumerate(pending_matches, 1):
        print(f"{Fore.CYAN}[{i}/{len(pending_matches)}]")
        print(f"{Fore.WHITE}Original: {Fore.YELLOW}{match['original_artist']} - {match['original_title']}")
        print(f"{Fore.WHITE}Spotify:  {Fore.GREEN}{match['spotify_artist']} - {match['spotify_title']}")
        print(f"{Fore.WHITE}Distance: {Fore.MAGENTA}{match['distance']:.1f}")
        
        while True:
            response = input(f"{Fore.YELLOW}Accept this match? (y/n/q to quit): ").strip().lower()
            if response in ['y', 'n', 'q']:
                break
            print(f"{Fore.RED}Invalid input. Please enter y, n, or q.")
        
        if response == 'q':
            print(f"{Fore.YELLOW}Skipping remaining confirmations...")
            break
        elif response == 'y':
            confirmed.append(match)
            print(f"{Fore.GREEN}✓ Accepted\n")
        else:
            print(f"{Fore.RED}✗ Rejected\n")
    
    print(f"{Fore.GREEN}✓ Confirmed {len(confirmed)} out of {len(pending_matches)} matches")
    return confirmed


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback from Spotify"""
    def do_GET(self):
        global auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if 'code' in params:
            auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: #1DB954;">Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authorization Failed</h1></body></html>")
    
    def log_message(self, format, *args):
        pass

class SpotifyAPI:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str = "http://localhost:8888/callback"):
        """Initialize with Spotify credentials"""
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_token = None
        self.user_token = None
        self.refresh_token = None
        
    def get_access_token(self) -> Optional[str]:
        """Authenticate with Spotify using Client Credentials"""
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode("utf-8")
        auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")
        
        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}
        
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            json_result = response.json()
            self.access_token = json_result["access_token"]
            return self.access_token
        except requests.exceptions.RequestException as e:
            print(f"{Fore.RED}✗ Error getting access token: {e}")
            return None
    
    def get_user_authorization(self) -> bool:
        """Start OAuth flow to get user authorization"""
        global auth_code
        auth_code = None
        
        scopes = "playlist-modify-public playlist-modify-private"
        
        auth_params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": scopes
        }
        
        auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(auth_params)
        
        print(f"\n{Fore.CYAN}{'=' * 60}")
        print(f"{Fore.CYAN}Opening browser for Spotify authorization...")
        print(f"{Fore.CYAN}{'=' * 60}")
        print(f"\n{Fore.YELLOW}If browser doesn't open, visit this URL:")
        print(f"{Fore.BLUE}{auth_url}")
        
        webbrowser.open(auth_url)
        
        print(f"\n{Fore.YELLOW}Starting local server on http://localhost:8888")
        print(f"{Fore.YELLOW}Waiting for authorization...")
        
        server = HTTPServer(('localhost', 8888), OAuthCallbackHandler)
        
        timeout = 120
        start_time = time.time()
        
        while auth_code is None and (time.time() - start_time) < timeout:
            server.handle_request()
        
        if auth_code is None:
            print(f"\n{Fore.RED}✗ Authorization timeout. Please try again.")
            return False
        
        print(f"{Fore.GREEN}✓ Authorization code received!")
        
        return self.get_user_token_from_code(auth_code)
    
    def get_user_token_from_code(self, code: str) -> bool:
        """Exchange authorization code for access token"""
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode("utf-8")
        auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")
        
        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri
        }
        
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            self.user_token = token_data.get("access_token")
            self.refresh_token = token_data.get("refresh_token")
            
            print(f"{Fore.GREEN}✓ User token obtained successfully!")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"{Fore.RED}✗ Error getting user token: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"{Fore.RED}Response: {e.response.text}")
            return False
    
    def search_song_with_fallback(self, artist: str, title: str) -> tuple[Optional[str], bool, Optional[Dict]]:
        """
        Search for a song and return the Spotify URI of the best match.
        Returns: (uri, needs_confirmation, match_data)
        """
        if not self.access_token:
            if not self.get_access_token():
                return None, False, None
        
        # First try: structured search
        query = f"artist:{artist} track:{title}"
        url = "https://api.spotify.com/v1/search"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {
            "q": query,
            "type": "track",
            "limit": 1
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            results = response.json()
            
            tracks = results.get("tracks", {}).get("items", [])
            if tracks:
                return tracks[0]["uri"], False, None
        except requests.exceptions.RequestException as e:
            # print(f"{Fore.RED}✗ Error during structured search: {e}")
            #if 429 Client Error
            if e.response.status_code == 429:
                print(f"{Fore.YELLOW}Rate limit exceeded. Retrying...")
                time.sleep(2)
                self.search_song_with_fallback(artist, title)
            pass
        
        # Second try: simple search with fuzzy matching
        query = f"{artist} - {title}"
        params = {
            "q": query,
            "type": "track",
            "limit": 10  # Get multiple results for comparison
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            results = response.json()
            
            tracks = results.get("tracks", {}).get("items", [])
            if tracks:
                # print(f"{Fore.YELLOW}Fuzzy matching for: {artist} - {title}")
                # for track in tracks:
                #     print(f"  Found: {', '.join([a['name'] for a in track.get('artists', [])])} - {track.get('name')}")
                best_match = find_best_match(artist, title, tracks)
                if best_match:
                    return best_match['uri'], best_match['needs_confirmation'], best_match
            
            return None, False, None
                
        except requests.exceptions.RequestException:
            return None, False, None

    def get_user_id(self) -> Optional[str]:
        """Get the current user's Spotify ID"""
        if not self.user_token:
            print(f"{Fore.RED}✗ Error: User token not set")
            return None
        
        url = "https://api.spotify.com/v1/me"
        headers = {
            "Authorization": f"Bearer {self.user_token}"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            user_data = response.json()
            return user_data.get("id")
        except requests.exceptions.RequestException as e:
            print(f"{Fore.RED}✗ Error getting user ID: {e}")
            return None
    
    def create_playlist(self, user_id: str, name: str, description: str = "", public: bool = False) -> Optional[str]:
        """Create a new playlist and return the playlist ID"""
        if not self.user_token:
            print(f"{Fore.RED}✗ Error: User token not set")
            return None
        
        url = f"https://api.spotify.com/v1/users/{user_id}/playlists"
        headers = {
            "Authorization": f"Bearer {self.user_token}",
            "Content-Type": "application/json"
        }
        data = {
            "name": name,
            "description": description,
            "public": public
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            playlist_data = response.json()
            return playlist_data.get("id")
        except requests.exceptions.RequestException as e:
            print(f"{Fore.RED}✗ Error creating playlist: {e}")
            return None
    
    def add_tracks_to_playlist(self, playlist_id: str, uris: List[str], batch_size: int = 100) -> bool:
        """Add tracks to a playlist (handles batching for large playlists)"""
        if not self.user_token:
            print(f"{Fore.RED}✗ Error: User token not set")
            return False
        
        url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        headers = {
            "Authorization": f"Bearer {self.user_token}",
            "Content-Type": "application/json"
        }
        
        with tqdm(total=len(uris), desc=f"{Fore.CYAN}Adding tracks", unit="track") as pbar:
            for i in range(0, len(uris), batch_size):
                batch = uris[i:i + batch_size]
                data = {
                    "uris": batch,
                    "position": i
                }
                
                try:
                    response = requests.post(url, headers=headers, json=data)
                    response.raise_for_status()
                    pbar.update(len(batch))
                    time.sleep(0.1)
                except requests.exceptions.RequestException as e:
                    print(f"\n{Fore.RED}✗ Error adding tracks to playlist: {e}")
                    return False
        
        return True

def get_all_episode_links(base_api_url, limit=12):
    """Paginate through the API to get all episode data"""
    all_episodes = []
    offset = 0
    
    print(f"{Fore.CYAN}Fetching episodes...")
    
    while True:
        api_url = f"{base_api_url}?offset={offset}&limit={limit}"
        
        response = requests.get(api_url)
        data = response.json()
        
        results = data.get('results', [])
        if not results:
            break
        
        for episode in results:
            episode_alias = episode.get('episode_alias')
            show_alias = episode.get('show_alias')
            broadcast = episode.get('broadcast')
            if episode_alias and show_alias:
                all_episodes.append({
                    'episode_alias': episode_alias,
                    'show_alias': show_alias,
                    'broadcast': broadcast
                })
        
        total_count = data.get('metadata', {}).get('resultset', {}).get('count', 0)
        offset += limit
        
        if offset >= total_count:
            break
    
    print(f"{Fore.GREEN}✓ Found {len(all_episodes)} episodes")
    return all_episodes

def get_episode_tracklist(show_alias, episode_alias):
    """Fetch full episode data including tracklist from the API"""
    api_url = f"https://www.nts.live/shows/{show_alias}/episodes/{episode_alias}"
    headers = {
        "accept": "application/json",
        "dnt": "1",
        "referer": f"https://www.nts.live/shows/{show_alias}/episodes/{episode_alias}",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        tracklist = data.get('tracklist', [])
        parsed_tracks = []
        
        for track in tracklist:
            main_artists = [artist.get('name') for artist in track.get('mainArtists', [])]
            featuring_artists = [artist.get('name') for artist in track.get('featuringArtists', [])]
            remix_artists = [artist.get('name') for artist in track.get('remixArtists', [])]
            
            all_artists = main_artists.copy()
            if featuring_artists:
                all_artists.append(f"ft. {', '.join(featuring_artists)}")
            if remix_artists:
                all_artists.append(f"({', '.join(remix_artists)} Remix)")
            
            artist_str = ", ".join(all_artists) if all_artists else "Unknown Artist"
            
            parsed_tracks.append({
                "artist": artist_str,
                "title": track.get('title', 'Unknown Title'),
                "offset": track.get('offset'),
                "duration": track.get('duration'),
                "uid": track.get('uid')
            })
        
        episode_data = {
            "broadcast_formatted": data.get('broadcast_formatted_long'),
            "mixcloud": data.get('mixcloud'),
            "audio_sources": data.get('audio_sources', [])
        }
        
        return parsed_tracks, episode_data
    
    except Exception as e:
        return [], {}

def process_episode(episode, delay=0.3):
    """Process a single episode"""
    show_alias = episode['show_alias']
    episode_alias = episode['episode_alias']
    broadcast = episode['broadcast']
    
    episode_url = f"https://www.nts.live/shows/{show_alias}/episodes/{episode_alias}"
    
    time.sleep(delay)
    
    tracklist, metadata = get_episode_tracklist(show_alias, episode_alias)
    
    tape_data = {
        "episode": episode_alias,
        "broadcast": broadcast,
        "broadcast_formatted": metadata.get('broadcast_formatted'),
        "url": episode_url,
        "mixcloud": metadata.get('mixcloud'),
        "audio_sources": metadata.get('audio_sources', []),
        "track_count": len(tracklist),
        "tracklist": tracklist
    }
    
    return tape_data

def search_single_track(track: Dict, spotify: SpotifyAPI) -> Dict:
    """Search for a single track on Spotify"""
    artist = track['artist']
    title = track['title']
    
    uri, needs_confirmation, match_data = spotify.search_song_with_fallback(artist, title)
    
    if uri:
        track_result = {
            **track,
            'spotify_uri': uri,
            'found': True
        }
        
        if needs_confirmation and match_data:
            track_result['pending_confirmation'] = True
            track_result['match_data'] = match_data
        
        return track_result
    else:
        return {
            **track,
            'spotify_uri': None,
            'found': False
        }

def search_tracks_on_spotify_parallel(tracks: List[Dict], spotify: SpotifyAPI, max_workers: int = 1) -> tuple[List[Dict], List[Dict]]:
    """
    Search for tracks on Spotify in parallel and return matches with URIs.
    Returns: (matched_tracks, pending_confirmations)
    """
    matched_tracks = [None] * len(tracks)  # Pre-allocate list to maintain order
    pending_confirmations = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_index = {
            executor.submit(search_single_track, track, spotify): i 
            for i, track in enumerate(tracks)
        }
        
        # Process completed tasks with progress bar
        with tqdm(total=len(tracks), desc=f"{Fore.CYAN}Searching Spotify", unit="track") as pbar:
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    matched_tracks[index] = result
                    
                    # Check if needs confirmation
                    if result.get('pending_confirmation') and result.get('match_data'):
                        pending_confirmations.append({
                            **result['match_data'],
                            'track_index': index
                        })
                    
                    pbar.update(1)
                    time.sleep(0.2)  # Small delay to avoid rate limiting
                except Exception as e:
                    # If search fails, mark as not found
                    matched_tracks[index] = {
                        **tracks[index],
                        'spotify_uri': None,
                        'found': False
                    }
                    pbar.update(1)
    
    return matched_tracks, pending_confirmations

def full_scrape_and_search(spotify: SpotifyAPI, show_alias: str):
    """Complete scrape of NTS and search on Spotify"""
    # Create data directory structure
    data_dir = os.path.join('data', show_alias)
    os.makedirs(data_dir, exist_ok=True)
    
    api_url = f"https://www.nts.live/api/v2/shows/{show_alias}/episodes"
    MAX_WORKERS = 5
    REQUEST_DELAY = 0.3
    
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"{Fore.CYAN}STEP 1: Fetching all episode links...")
    print(f"{Fore.CYAN}{'=' * 60}")
    episodes = get_all_episode_links(api_url)
    total_episodes = len(episodes)
    
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"{Fore.CYAN}STEP 2: Processing {total_episodes} episodes...")
    print(f"{Fore.CYAN}{'=' * 60}\n")
    
    all_tapes = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_episode, episode, REQUEST_DELAY) for episode in episodes]
        
        with tqdm(total=total_episodes, desc=f"{Fore.CYAN}Processing episodes", unit="episode") as pbar:
            for future in as_completed(futures):
                try:
                    tape_data = future.result()
                    all_tapes.append(tape_data)
                    pbar.update(1)
                except Exception as e:
                    pbar.update(1)
    
    all_tapes.sort(key=lambda x: x['broadcast'], reverse=True)
    
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"{Fore.CYAN}STEP 3: Searching tracks on Spotify (parallel)...")
    print(f"{Fore.CYAN}{'=' * 60}\n")
    
    # Collect all tracks from all episodes
    all_tracks = []
    tape_track_mapping = []  # Keep track of which tracks belong to which tape
    
    for tape_idx, tape in enumerate(all_tapes):
        tape_start = len(all_tracks)
        if tape['track_count'] > 0:
            all_tracks.extend(tape['tracklist'])
        tape_end = len(all_tracks)
        tape_track_mapping.append((tape_idx, tape_start, tape_end))
    
    # Search all tracks in parallel
    if all_tracks:
        matched_tracks, all_pending_confirmations = search_tracks_on_spotify_parallel(
            all_tracks, spotify, max_workers=SPOTIFY_SEARCH_MAX_WORKERS
        )
        
        # Redistribute matched tracks back to their tapes
        for tape_idx, start_idx, end_idx in tape_track_mapping:
            all_tapes[tape_idx]['tracklist'] = matched_tracks[start_idx:end_idx]
        
        # Confirm fuzzy matches
        if all_pending_confirmations:
            confirmed_matches = confirm_matches(all_pending_confirmations)
            
            # Update tracks based on confirmations
            confirmed_indices = {m['track_index'] for m in confirmed_matches}
            rejection_count = 0
            
            # Find and update rejected matches
            current_index = 0
            for tape in all_tapes:
                for track in tape['tracklist']:
                    if track.get('pending_confirmation'):
                        if current_index not in confirmed_indices:
                            # User rejected this match
                            track['spotify_uri'] = None
                            track['found'] = False
                            rejection_count += 1
                        # Clean up temporary fields
                        track.pop('pending_confirmation', None)
                        track.pop('match_data', None)
                    current_index += 1
            
            print(f"\n{Fore.CYAN}✓ Rejected {rejection_count} fuzzy matches")
    
    # Save results
    output_file = os.path.join(data_dir, 'tracklists_with_spotify.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_tapes, indent=2, fp=f, ensure_ascii=False)
    
    # Generate playlist URIs
    all_uris = []
    for tape in all_tapes:
        for track in tape['tracklist']:
            if track.get('spotify_uri'):
                all_uris.append(track['spotify_uri'])
    
    playlist_data = {
        'show_alias': show_alias,
        'name': f'NTS RADIO - {show_alias.upper()} Collection',
        'description': f'Tracks from {show_alias} shows on NTS Radio, compiled by (www.github.com/charlie-adam/nts_scraper)',
        'total_tracks': len(all_uris),
        'uris': all_uris
    }
    
    playlist_file = os.path.join(data_dir, 'playlist_uris.json')
    with open(playlist_file, 'w', encoding='utf-8') as f:
        json.dump(playlist_data, indent=2, fp=f)
    
    # Summary
    total_tracks = sum(tape['track_count'] for tape in all_tapes)
    print(f"\n{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.GREEN}COMPLETE!")
    print(f"{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.GREEN}✓ Episodes processed: {len(all_tapes)}")
    print(f"{Fore.GREEN}✓ Total tracks: {total_tracks}")
    print(f"{Fore.GREEN}✓ Tracks found on Spotify: {len(all_uris)}")
    print(f"{Fore.GREEN}✓ Match rate: {len(all_uris)/total_tracks*100:.1f}%")
    print(f"\n{Fore.YELLOW}✓ Full data saved to: {output_file}")
    print(f"{Fore.YELLOW}✓ Playlist URIs saved to: {playlist_file}")
     
def retry_failed_tracks(spotify: SpotifyAPI, show_alias: str):
    """Retry searching for tracks that weren't found"""
    data_dir = os.path.join('data', show_alias)
    input_file = os.path.join(data_dir, 'tracklists_with_spotify.json')
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            all_tapes = json.load(f)
    except FileNotFoundError:
        print(f"{Fore.RED}✗ Error: {input_file} not found")
        print(f"{Fore.YELLOW}Please run option 1 first to generate the file")
        return
    
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"{Fore.CYAN}Retrying failed track searches (parallel)...")
    print(f"{Fore.CYAN}{'=' * 60}\n")
    
    # Collect failed tracks with their positions
    failed_tracks_info = []
    for tape_idx, tape in enumerate(all_tapes):
        for track_idx, track in enumerate(tape['tracklist']):
            if not track.get('found', False):
                failed_tracks_info.append({
                    'tape_idx': tape_idx,
                    'track_idx': track_idx,
                    'track': track
                })
    
    if not failed_tracks_info:
        print(f"{Fore.GREEN}✓ No failed tracks to retry!")
        return
    
    print(f"{Fore.CYAN}Found {len(failed_tracks_info)} failed tracks to retry\n")
    
    # Extract just the tracks for searching
    failed_tracks = [info['track'] for info in failed_tracks_info]
    
    # Search all failed tracks in parallel
    matched_tracks, pending_confirmations = search_tracks_on_spotify_parallel(
        failed_tracks, spotify, max_workers=SPOTIFY_SEARCH_MAX_WORKERS
    )
    
    # Update the original tapes with results
    total_found = 0
    for i, info in enumerate(failed_tracks_info):
        result = matched_tracks[i]
        tape_idx = info['tape_idx']
        track_idx = info['track_idx']
        
        all_tapes[tape_idx]['tracklist'][track_idx] = result
        
        if result.get('found'):
            total_found += 1
            
            # Add position info to pending confirmations
            if result.get('pending_confirmation'):
                for confirmation in pending_confirmations:
                    if confirmation.get('track_index') == i:
                        confirmation['tape_idx'] = tape_idx
                        confirmation['track_idx'] = track_idx
                        break
    
    # Confirm fuzzy matches
    if pending_confirmations:
        confirmed_matches = confirm_matches(pending_confirmations)
        
        # Update tracks based on confirmations
        confirmed_set = {(m['tape_idx'], m['track_idx']) for m in confirmed_matches}
        rejection_count = 0
        
        for match in pending_confirmations:
            tape_idx = match['tape_idx']
            track_idx = match['track_idx']
            
            if (tape_idx, track_idx) not in confirmed_set:
                # User rejected this match
                all_tapes[tape_idx]['tracklist'][track_idx]['spotify_uri'] = None
                all_tapes[tape_idx]['tracklist'][track_idx]['found'] = False
                total_found -= 1
                rejection_count += 1
            
            # Clean up temporary field
            all_tapes[tape_idx]['tracklist'][track_idx].pop('pending_confirmation', None)
            all_tapes[tape_idx]['tracklist'][track_idx].pop('match_data', None)
        
        print(f"\n{Fore.CYAN}✓ Rejected {rejection_count} fuzzy matches")
    
    # Save updated results
    with open(input_file, 'w', encoding='utf-8') as f:
        json.dump(all_tapes, indent=2, fp=f, ensure_ascii=False)
    
    # Update playlist URIs
    all_uris = []
    for tape in all_tapes:
        for track in tape['tracklist']:
            if track.get('spotify_uri'):
                all_uris.append(track['spotify_uri'])
    
    playlist_data = {
        'show_alias': show_alias,
        'name': f'NTS RADIO - {show_alias.upper()} Collection',
        'description': f'Tracks from {show_alias} shows on NTS Radio, compiled by (www.github.com/charlie-adam/nts_scraper)',
        'total_tracks': len(all_uris),
        'uris': all_uris
    }
    
    playlist_file = os.path.join(data_dir, 'playlist_uris.json')
    with open(playlist_file, 'w', encoding='utf-8') as f:
        json.dump(playlist_data, indent=2, fp=f)
    
    print(f"\n{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.GREEN}RETRY COMPLETE!")
    print(f"{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.GREEN}✓ Tracks retried: {len(failed_tracks_info)}")
    print(f"{Fore.GREEN}✓ New matches found: {total_found}")
    print(f"{Fore.GREEN}✓ Total tracks in playlist: {len(all_uris)}")
    
def create_spotify_playlist(spotify: SpotifyAPI, show_alias: str):
    """Create playlist on Spotify from saved URIs"""
    data_dir = os.path.join('data', show_alias)
    playlist_file = os.path.join(data_dir, 'playlist_uris.json')
    
    try:
        with open(playlist_file, 'r', encoding='utf-8') as f:
            playlist_data = json.load(f)
    except FileNotFoundError:
        print(f"{Fore.RED}✗ Error: {playlist_file} not found")
        print(f"{Fore.YELLOW}Please run option 1 or 2 first to generate the file")
        return
    
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"{Fore.CYAN}Creating Spotify Playlist...")
    print(f"{Fore.CYAN}{'=' * 60}\n")
    
    # Get user authorization if not already done
    if not spotify.user_token:
        print(f"{Fore.YELLOW}User authorization required...")
        if not spotify.get_user_authorization():
            print(f"{Fore.RED}✗ Failed to get user authorization")
            return
    
    # Get user ID
    print(f"\n{Fore.CYAN}Getting user information...")
    user_id = spotify.get_user_id()
    if not user_id:
        print(f"{Fore.RED}✗ Failed to get user ID. Please try authorizing again.")
        return
    print(f"{Fore.GREEN}✓ User ID: {user_id}")
    
    # Create playlist
    playlist_name = playlist_data.get('name', f'{show_alias.upper()} Collection')
    playlist_desc = playlist_data.get('description', f'All tracks from {show_alias} shows on NTS Radio')
    
    print(f"\n{Fore.CYAN}Creating playlist: {playlist_name}")
    playlist_id = spotify.create_playlist(user_id, playlist_name, playlist_desc, public=False)
    
    if not playlist_id:
        print(f"{Fore.RED}✗ Failed to create playlist")
        return
    
    print(f"{Fore.GREEN}✓ Playlist created! ID: {playlist_id}")
    playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    print(f"{Fore.BLUE}✓ URL: {playlist_url}")
    
    # Add tracks
    uris = playlist_data.get('uris', [])
    print(f"\n{Fore.CYAN}Adding {len(uris)} tracks to playlist...")
    
    success = spotify.add_tracks_to_playlist(playlist_id, uris)
    
    if success:
        print(f"\n{Fore.GREEN}{'=' * 60}")
        print(f"{Fore.GREEN}PLAYLIST CREATED SUCCESSFULLY!")
        print(f"{Fore.GREEN}{'=' * 60}")
        print(f"{Fore.GREEN}✓ Playlist: {playlist_name}")
        print(f"{Fore.GREEN}✓ Total tracks: {len(uris)}")
        print(f"{Fore.BLUE}✓ URL: {playlist_url}")
    else:
        print(f"\n{Fore.RED}✗ Error: Failed to add all tracks to playlist")

def show_menu():
    """Display menu options"""
    print(f"\n{Fore.MAGENTA}{'=' * 60}")
    print(f"{Fore.MAGENTA}NTS RADIO → SPOTIFY PLAYLIST CREATOR")
    print(f"{Fore.MAGENTA}{'=' * 60}")
    print(f"\n{Fore.CYAN}1. Full scrape and search (NTS → Spotify)")
    print(f"{Fore.CYAN}2. Retry failed tracks (search null spotify_uri)")
    print(f"{Fore.CYAN}3. Create Spotify playlist from URIs")
    print(f"{Fore.CYAN}4. Exit")
    print(f"\n{Fore.MAGENTA}{'=' * 60}")

if __name__ == "__main__":
    # Load credentials from environment
    CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print(f"{Fore.RED}✗ Error: Missing Spotify credentials in .env file")
        print(f"{Fore.YELLOW}Please create a .env file with:")
        print(f"{Fore.YELLOW}SPOTIFY_CLIENT_ID=your_client_id")
        print(f"{Fore.YELLOW}SPOTIFY_CLIENT_SECRET=your_client_secret")
        exit(1)
    
    # Initialize Spotify API
    spotify = SpotifyAPI(CLIENT_ID, CLIENT_SECRET)
    spotify.get_access_token()
    
    # Get show alias
    show_alias = input(f"\n{Fore.YELLOW}Enter NTS show alias (e.g., 'm00dtapes'): ").strip().lower()
    
    if not show_alias:
        print(f"{Fore.RED}✗ Show alias cannot be empty")
        exit(1)
    
    while True:
        show_menu()
        choice = input(f"{Fore.YELLOW}Select option (1-4): ").strip()
        
        if choice == "1":
            full_scrape_and_search(spotify, show_alias)
        
        elif choice == "2":
            retry_failed_tracks(spotify, show_alias)
        
        elif choice == "3":
            create_spotify_playlist(spotify, show_alias)
        
        elif choice == "4":
            print(f"\n{Fore.CYAN}Exiting... Goodbye!")
            break
        
        else:
            print(f"\n{Fore.RED}✗ Invalid option. Please select 1-4.")
        
        input(f"\n{Fore.YELLOW}Press Enter to continue...")