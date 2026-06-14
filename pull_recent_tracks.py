import pandas as pd
import json
import numpy as np
from pathlib import Path
from datetime import datetime
from spotify_data_collection import data, sp
from spotify_helper_funs import  get_song_info, write_to_supabase, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, supabase, read_from_supabase
from playlist_builder import update_playlist

print('Running at', datetime.now())


results = sp.current_user_recently_played(limit=50)

res_df = pd.DataFrame([{
    'ts': item['played_at'],
    'spotify_track_uri': item['track']['uri'],
    'master_metadata_album_artist_name': item['track']['album']['artists'][0]['name'],
    'master_metadata_album_album_name': item['track']['album']['name'],
    'master_metadata_track_name': item['track']['name'],
    'type': item['track']['type'],
    'time_added': datetime.now().isoformat()
} for item in results['items']])

latest_timestamp = supabase.table('SpotifyStreams').select("ts").order('ts', desc=True).limit(1).execute().data[0]['ts']

if len(latest_timestamp) > 0:
    res_df = res_df[pd.to_datetime(res_df['ts'], format='ISO8601', utc=True) > pd.to_datetime(latest_timestamp)]

if len(res_df) > 0:
    print('Writing streamed songs to database...')
    write_to_supabase('SpotifyStreams', res_df)

latest_liked_song_timestamp = supabase.table('SpotifyLikedSongs').select("added_at").order('added_at', desc=True).limit(1).execute().data[0]['added_at']

offset = 0
still_data_to_pull = True
saved_tracks_to_add = pd.DataFrame({
        'uri': [],
        'album': [],
        'artist': [],
        'track': [],
        'added_at': []
})
while still_data_to_pull:
    saved_tracks = sp.current_user_saved_tracks(offset = offset)['items']
    if len(saved_tracks) > 0:
        saved_tracks_df = pd.DataFrame([{
            'uri': item['track']['uri'],
            'album': item['track']['album']['name'],
            'artist': item['track']['album']['artists'][0]['name'],
            'track': item['track']['name'],
            'added_at': item['added_at']
        } for item in saved_tracks])
        saved_tracks_df = saved_tracks_df[pd.to_datetime(saved_tracks_df['added_at'], format='ISO8601', utc=True) > latest_liked_song_timestamp]
        if(len(saved_tracks_df) > 0):
            saved_tracks_to_add = pd.concat([saved_tracks_to_add, saved_tracks_df], axis = 0)
        if len(saved_tracks_df) < 20:
            still_data_to_pull = False
    else:
        still_data_to_pull = False
    offset += 20

if len(saved_tracks_df) > 0:
    print('Writing liked songs to database...')
    write_to_supabase('SpotifyLikedSongs', saved_tracks_df)

subscriptions = read_from_supabase(table_name = 'PlaylistSubscriptions')
subscriptions = subscriptions[subscriptions['refresh'] == 'hourly']

if len(subscriptions[(subscriptions['playlist_type'] == 'LikedSongsMultiBands') & (subscriptions['refresh'] == 'hourly')]) > 0:
    artists_with_new_liked_songs = np.unique(saved_tracks_df['artist'])
    subscriptions_to_update = subscriptions[subscriptions['band_list'].str.contains('|'.join(artists_with_new_liked_songs))]
    if len(subscriptions_to_update) > 0:
        for sub in range(len(subscriptions_to_update)):
            this_sub = subscriptions_to_update.iloc[[sub]]
            artists_this_sub = this_sub['band_list'].str.split('|')[0]
            update_playlist(subscription_id = this_sub['id'][0],
                            new_songs = saved_tracks_df[saved_tracks_df['artist'].isin(artists_this_sub)]['uri'], remove = False)

#song info:
#%%
# recent_streams = read_from_supabase(table_name = 'SpotifyStreams', chunk_size = 1000).drop(columns = ['time_added','type'])

# json_path = Path('/Users/izzybeers/Documents/spotify_project/data')
# print(f"Cron woke up in: {Path.cwd()}")

# extended_data = pd.DataFrame()
# for file in sorted(json_path.rglob('*.json')):
#     with open(file, 'r') as data_file:
#         extended_data = pd.concat([extended_data, pd.DataFrame(json.load(data_file))], axis = 0)
# data = pd.concat([extended_data,recent_streams], axis = 0)

uris_already_pulled = read_from_supabase(table_name = 'SpotifySongInfo',
                                         select = 'added_at, uri',
                                         chunk_size = 1000)

print(f"Last time the spotify song info has been pulled:", max(pd.to_datetime(uris_already_pulled['added_at'])))

uris_to_add_now  = data[~(data['spotify_track_uri'].isin(uris_already_pulled['uri']))]['spotify_track_uri'].unique()[0:100]

# print(f"{len(recent_streams)} number of recent streams")
# print(f"{len(extended_data)} rows in main data")
print(f"{len(uris_already_pulled)} uris already pulled")
# print(uris_already_pulled)
print(f"{len(uris_to_add_now)} songs to pull info for...")

song_info = get_song_info(uri_list = uris_to_add_now, sp = sp)

song_info['release_date'] = pd.to_datetime(song_info['release_date'], format='mixed', errors='coerce')
song_info['release_date'] = song_info['release_date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else None)
song_info['added_at'] = song_info['added_at'].astype(str).replace('NaT', None)

if len(song_info) > 0:
    print('writing song info to database...')
    write_to_supabase('SpotifySongInfo', song_info)


#%%

