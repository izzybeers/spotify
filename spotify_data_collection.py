import json
import pandas as pd
import numpy as np
import os
from pathlib import Path
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
from supabase import create_client, Client
from spotify_helper_funs import get_song_info, write_to_supabase, read_from_supabase

CLIENT_ID = "4e8269446f474d3f920be9dfa56086d5"
CLIENT_SECRET = "69f0f2b62b924d458d14a45a526cd5ed"
REDIRECT_URI = "http://127.0.0.1:9090/callback" # Must match your Spotify Dashboard

supabase_api_key = 'sb_publishable_CRS7gXJPt2eGRZ2QyfMHWQ_tFqFZcSj'
supabase_endpoint= 'https://vciwmitbqbfjcrrxgcmb.supabase.co'
supabase: Client = create_client(supabase_endpoint, supabase_api_key)

#os.chdir('../Downloads/spotify_project')

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope = (
    "user-library-read user-library-modify "
    "playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private "
    "user-top-read user-read-recently-played "
    "user-follow-read user-follow-modify "
    "ugc-image-upload"
),
    cache_handler=CacheFileHandler(cache_path='spotify_token.txt'),
    open_browser=False
))


recent_streams = read_from_supabase(table_name = 'SpotifyStreams', chunk_size = 1000).drop(columns = ['time_added','type'])

json_path = Path('/Users/izzybeers/Documents/spotify_project/data')

data = pd.DataFrame()
for file in sorted(json_path.rglob('*.json')):
    with open(file, 'r') as data_file:
        data = pd.concat([data, pd.DataFrame(json.load(data_file))], axis = 0)
data = pd.concat([data,recent_streams], axis = 0)
data['year'] = data['ts'].str.slice(0,4)
data['year_month'] = data['ts'].str.slice(0,7)
data['day'] = pd.to_datetime(data['ts'].str.slice(0,10))
data['display_name'] = data['master_metadata_album_artist_name'] + ' - ' + data['master_metadata_track_name']
#change this once we have song duration, so it would be min of 60,000ms and 50% of the songs duration (for shorter songs)
data = data.query('ms_played > 60000')

liked_songs = read_from_supabase(table_name = 'SpotifyLikedSongs',
                                 chunk_size = 1000)