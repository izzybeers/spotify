#%% import pandas as pd
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, date
from spotify_data_collection import data, sp, sp_alex
from spotify_helper_funs import  get_song_info, write_to_supabase, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, supabase, read_from_supabase, get_songs_on_playlist
from playlist_builder import update_playlist, top_n_songs_by_band

print('Running at', datetime.now())

for sp_user in [sp, sp_alex]:

    user_id = sp_user.current_user()['id']
    user_name = sp_user.current_user()['display_name']

    print(f"Running data for {user_name}")

    results = sp_user.current_user_recently_played(limit=50)

    res_df = pd.DataFrame([{
        'ts': item['played_at'],
        'spotify_track_uri': item['track']['uri'],
        'master_metadata_album_artist_name': item['track']['album']['artists'][0]['name'],
        'master_metadata_album_album_name': item['track']['album']['name'],
        'master_metadata_track_name': item['track']['name'],
        'type': item['track']['type'],
        'time_added': datetime.now().isoformat(),
        'user_id': user_id,
        'user_name': user_name
    } for item in results['items']])

    if sp_user == sp:
        res_df = res_df.merge(data.drop_duplicates(subset=['spotify_track_uri']).groupby('spotify_track_uri', as_index = False).agg(artist = ('master_metadata_album_artist_name', 'first')), on = 'spotify_track_uri', how = 'left')\
            .assign(master_metadata_album_artist_name = lambda x: np.where(x['artist'].notna() & (x['master_metadata_album_artist_name'] != x['artist']), x['artist'], x['master_metadata_album_artist_name']))\
                .drop(columns = ['artist'])

    latest_timestamp = supabase.table('SpotifyStreams').select("ts").eq('user_id', user_id).order('ts', desc=True).limit(1).execute().data

    if len(latest_timestamp) > 0:
        latest_timestamp = latest_timestamp[0]['ts']
        res_df = res_df[pd.to_datetime(res_df['ts'], format='ISO8601', utc=True) > pd.to_datetime(latest_timestamp)]

    if len(res_df) > 0:
        print(f"Writing {len(res_df)} streamed songs to database...")
        write_to_supabase('SpotifyStreams', res_df)
    else:
        print('No new tracks.')

    latest_liked_song_timestamp = supabase.table('SpotifyLikedSongs').select("added_at").eq('user_id',user_id).order('added_at', desc=True).limit(1).execute().data
    if len(latest_liked_song_timestamp) > 0:
        latest_liked_song_timestamp = latest_liked_song_timestamp[0]['added_at']

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
        saved_tracks = sp_user.current_user_saved_tracks(offset = offset)['items']
        if len(saved_tracks) > 0:
            saved_tracks_df = pd.DataFrame([{
                'uri': item['track']['uri'],
                'album': item['track']['album']['name'],
                'artist': item['track']['album']['artists'][0]['name'],
                'track': item['track']['name'],
                'added_at': item['added_at'],
                'user_id': user_id,
                'user_name': user_name
            } for item in saved_tracks])
            if len(latest_liked_song_timestamp) > 0:
                saved_tracks_df = saved_tracks_df[pd.to_datetime(saved_tracks_df['added_at'], format='ISO8601', utc=True) > latest_liked_song_timestamp]
            if(len(saved_tracks_df) > 0):
                saved_tracks_to_add = pd.concat([saved_tracks_to_add, saved_tracks_df], axis = 0)
            if len(saved_tracks_df) < 20:
                still_data_to_pull = False
        else:
            still_data_to_pull = False
        offset += 20

    if len(saved_tracks_to_add) > 0:
        print('Writing liked songs to database...')
        write_to_supabase('SpotifyLikedSongs', saved_tracks_to_add)
    else:
        print('No new liked songs to add.')

    subscriptions = read_from_supabase(table_name = 'PlaylistSubscriptions')
    subscriptions = subscriptions[subscriptions['refresh'] == 'hourly']

    #make the "top n songs" option work here

    if len(subscriptions[(subscriptions['playlist_type'] == 'LikedSongsMultiBands') & (subscriptions['refresh'] == 'hourly') & (subscriptions['user_id'] == user_id)]) > 0:
        artists_with_new_liked_songs = np.unique(saved_tracks_to_add['artist'])
        if len(artists_with_new_liked_songs) > 0:
            subscriptions_to_update = subscriptions[(subscriptions['playlist_type'] == 'LikedSongsMultiBands') & (subscriptions['param_list'].str.contains('|'.join(artists_with_new_liked_songs))) & (subscriptions['refresh'] == 'hourly')]
            if len(subscriptions_to_update) > 0:
                for sub in range(len(subscriptions_to_update)):
                    this_sub = subscriptions_to_update.iloc[[sub]]
                    artists_this_sub = this_sub['param_list'].str.split('|')
                    update_playlist(subscription_id = this_sub.iloc[0]['id'],
                                    new_songs = saved_tracks_to_add[saved_tracks_to_add['artist'].isin(artists_this_sub.iloc[0])]['uri'], 
                                    sp = sp_user,
                                    remove = False)

    if len(subscriptions[(subscriptions['playlist_type'] == 'TopSongsMultiBands') & (subscriptions['refresh'] == 'hourly') & (subscriptions['user_id'] == user_id)]) > 0:
        if len(res_df) > 0: #if no new streams in the past hour, no need to refresh streaming playlist
            artists_streamed = np.unique(res_df['master_metadata_album_artist_name'])
            subscriptions_to_update = subscriptions[(subscriptions['playlist_type'] == 'TopSongsMultiBands') & (subscriptions['param_list'].str.contains('|'.join(artists_streamed))) & (subscriptions['refresh'] == 'hourly')]
            if len(subscriptions_to_update) > 0:
                for sub in range(len(subscriptions_to_update)):
                    this_sub = subscriptions_to_update.iloc[[sub]]
                    artists, n, time_range = this_sub['param_list'].str.split(';').iloc[0]
                    artists_this_sub = artists.split('|')
                    songs = pd.concat([
                                data.rename(columns={
                                    'master_metadata_album_artist_name': 'artist',
                                    'master_metadata_track_name': 'track',
                                    'spotify_track_uri': 'uri'
                                }),
                                res_df.rename(columns={
                                    'master_metadata_album_artist_name': 'artist',
                                    'master_metadata_track_name': 'track',
                                    'spotify_track_uri': 'uri'
                                })
                            ])
                    song_list = top_n_songs_by_band(songs, artists_this_sub, int(n), time_range)
        
                    update_playlist(subscription_id = this_sub.iloc[0]['id'],
                                    new_songs = song_list, 
                                    sp = sp_user,
                                    remove = True)
                    
    if len(subscriptions[(subscriptions['playlist_type'] == 'CombinePlaylists') & (subscriptions['refresh'] == 'hourly') & (subscriptions['user_id'] == user_id)]) > 0:
        subscriptions_to_consider= subscriptions[subscriptions['playlist_type'] == 'CombinePlaylists']
        for s_indx in range(len(subscriptions_to_consider)):
            sub = subscriptions_to_consider.iloc[[s_indx]]
            songs_in_combined_playlist = get_songs_on_playlist(sub['playlist_id'].iloc[0], sp)['uri']
            total_individual_playlists_song_list = []
            for p in sub['param_list'].str.split('|').iloc[0]:
                songs_in_this_playlist = get_songs_on_playlist(p, sp)['uri']
                total_individual_playlists_song_list.extend(songs_in_this_playlist)
            if len(set(total_individual_playlists_song_list) - set(songs_in_combined_playlist)) +\
                len(set(songs_in_combined_playlist) - set(total_individual_playlists_song_list)) > 0:
                update_playlist(subscription_id = sub['id'].iloc[0],
                                new_songs = total_individual_playlists_song_list, 
                                sp = sp_user,
                                remove = True)
            
#song info:

uris_already_pulled = read_from_supabase(table_name = 'SpotifySongInfo',
                                         select = 'added_at, uri',
                                         chunk_size = 500)

last_time_run = max(pd.to_datetime(uris_already_pulled['added_at']))
print(f"Last time the spotify song info has been pulled: {last_time_run}")

uris_to_add_now  = data[~(data['spotify_track_uri'].isin(uris_already_pulled['uri']))]['spotify_track_uri'].unique()[0:10]

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

