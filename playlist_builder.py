#%%
import json
import pandas as pd
import random
import numpy as np
import os
import time
from pathlib import Path
from datetime import datetime
from spotify_helper_funs import get_song_info, write_to_supabase, update_supabase_rows, read_from_supabase, get_followed_playlists, get_songs_on_playlist
from spotify_data_collection import data, sp, supabase, liked_songs

#%%

#%%
subscriptions = read_from_supabase(table_name = 'PlaylistSubscriptions')

def name_playlist(playlist_type, band_list = None, n = None, combine_playlists = None):
    if playlist_type ==  'LikedSongsMultiBands':
        if band_list is None:
            print('Error: band_list must be provided for playlist type LikedSongsMultiBands')
        else:
            name = f"Liked songs from {', '.join(band_list[0:3])}{' and more' if len(band_list) > 3 else ''}"
            description = f"Liked songs from {', '.join(band_list)}"
    elif playlist_type == 'CombinePlaylists':
        if combine_playlists is None:
            print('Error: playlist_names parameter must not be empty.')
        else:
            playlist_names = combine_playlists['name']
            name = f"Combined Playlists: {', '.join(playlist_names[0:3])}{', and more' if len(playlist_names) > 3 else ''}"
            description = f"Combined Playlists: {', '.join(playlist_names)}"
    elif playlist_type == 'TopSongsMultiBands':
        if band_list is None:
            print('Error: band_list must be provided for playlist type LikedSongsMultiBands')
        else:
            name = f"Top {n} songs from {', '.join(band_list[0:3])}{' and more' if len(band_list) > 3 else ''}"
            description = f"Top {n} songs from {', '.join(band_list)}"
    return [name, description]

def add_new_playlist(playlist_type, public, user_id, user_name, refresh, liked_songs = None, band_list = None, n = None, combine_playlists = None):
    if playlist_type ==  'LikedSongsMultiBands':
        if band_list is None:
            print('Error: band_list must be provided for playlist type LikedSongsMultiBands')
        else:
            name, description = name_playlist(playlist_type, band_list)
            param_list = band_list
            initial_songs_to_add = liked_songs[liked_songs['artist'].isin(band_list)]\
                .assign(display_name = lambda x: x['artist'] +  '-' + x['track'])\
                    .sort_values(by = 'added_at', ascending = False)\
                        .drop_duplicates(subset = 'display_name', keep = 'first')['uri']
    elif playlist_type == 'CombinePlaylists':
        if (combine_playlists is None) | (len(combine_playlists) > 5) | (len(combine_playlists) == 1):
            print('Error: must specify between 2 and 5 playlists to combine.')
        else:
            name, description = name_playlist(playlist_type = playlist_type,
                                              combine_playlists = combine_playlists)
            param_list = combine_playlists['id']
            initial_songs_to_add = pd.DataFrame()
            for p in combine_playlists['id']:
                initial_songs_to_add = pd.concat([initial_songs_to_add,
                                                  pd.DataFrame(get_songs_on_playlist(p, sp))])
            initial_songs_to_add['display_name'] = initial_songs_to_add['artist'] + '-' + initial_songs_to_add['name']
            initial_songs_to_add = initial_songs_to_add.drop_duplicates(subset = 'display_name', keep = 'first').sort_values('artist')['uri']
    elif playlist_type == 'TopSongsMultiBands':
        if (band_list is None) | (len(band_list) <= 1) | (n is None):
            print('Error: must specify more than one band and a value of n.')
        else:
            name, description = name_playlist(playlist_type = playlist_type,
                                              band_list = band_list,
                                              n = n)
            param_list = band_list
             #defined by top streams:
            initial_songs_to_add = liked_songs[liked_songs['artist'].isin(band_list)]\
            .assign(num_streams = lambda x: x.groupby(['artist','track'])['uri'].transform('size'))\
            .drop_duplicates(subset = ['artist','track'], keep = 'first')\
                .assign(display_name = lambda x: x['artist'] +  '-' + x['track'],
                        rank_streams = lambda x: x.groupby('artist')['num_streams'].rank(method = 'first', ascending = False))\
                        .query("rank_streams <= @n")['uri']


    new_playlist = sp.current_user_playlist_create(name = name,
                                                   public = public,
                                                   collaborative = False,
                                                   description = description)
    new_subscription_id = random.randint(1, 1000000)
    data_to_write = pd.DataFrame({
        'id': [new_subscription_id],
        'user_id': [user_id],
        'playlist_type': [playlist_type],
        'playlist_id': [new_playlist['id']],
        'playlist_uri': [new_playlist['uri']],
        'param_list': ['|'.join(param_list)],
        'created_at': [pd.Timestamp.now(tz='UTC').isoformat()],
        'subscription_updated_at': [pd.Timestamp.now(tz='UTC').isoformat()],
        'playlist_updated_at': [pd.Timestamp.now(tz='UTC').isoformat()],
        'Active': [1],
        'refresh': [refresh],
        'public': [public],
        'Description': [user_name + ': ' + name]
    })
    write_to_supabase(table_name = 'PlaylistSubscriptions', df = data_to_write)
    
    
    update_playlist(subscription_id = new_subscription_id,
                    new_songs = initial_songs_to_add,
                    sp = sp,
                    remove = True)
    return new_subscription_id

def update_playlist(subscription_id, new_songs, sp, remove = False):
    playlist_id = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                 select = 'playlist_id',
                                 eq_col_name = 'id',
                                 eq_value = subscription_id).iloc[0]['playlist_id']
    songs_on_playlist = get_songs_on_playlist(playlist_id, sp)
    if len(songs_on_playlist)>0:
        songs_on_playlist = songs_on_playlist['uri']
        songs_to_add = set(new_songs) - set(songs_on_playlist)
        songs_to_remove = set(songs_on_playlist) - set(new_songs)
    else:
        songs_to_add = set(new_songs)
        songs_to_remove = []
    if len(songs_to_add) > 0:
        try:
            for i in range(np.ceil(len(songs_to_add)/100).astype(int)):
                start_idx = i*100
                end_idx = min(start_idx + 100, len(songs_to_add))
                sp.playlist_add_items(playlist_id = playlist_id,
                                    items = list(songs_to_add)[start_idx:end_idx])
            print(f"Added {len(songs_to_add)} songs to playlist")
            update_supabase_rows(table_name = 'PlaylistSubscriptions',
                         match_column = 'id',
                         match_column_value = subscription_id,
                         new_row = {'playlist_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
        except Exception as e:
            print(f"Error adding tracks: {e}")
    if remove:   
        if len(songs_to_remove) > 0:
            try:
                for i in range(np.ceil(len(songs_to_remove)/100).astype(int)):
                    start_idx = i*100
                    end_idx = min(start_idx + 100, len(songs_to_remove))
                    sp.playlist_remove_all_occurrences_of_items(playlist_id = playlist_id,
                                                                items = list(songs_to_remove)[start_idx:end_idx])
                print(f"Removed {len(songs_to_remove)} songs from playlist")
                update_supabase_rows(table_name = 'PlaylistSubscriptions',
                            match_column = 'id',
                            match_column_value = subscription_id,
                            new_row = {'playlist_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
            except Exception as e:
                print(f"Error removing tracks")
    else:
        songs_to_remove = []
    if (len(songs_to_add) == 0) & (len(songs_to_remove) == 0):
        print(f"No updates for {subscription_id}")


def update_subscription_refresh_rate(subscription_id, new_refresh):
    update_supabase_rows(table_name = 'PlaylistSubscriptions',
                         match_column = 'id',
                         match_column_value = subscription_id,
                         new_row = {'refresh': new_refresh, 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
    
def update_subscription_band_list(subscription_id, user_name, new_band_list, liked_songs):
    liked_songs_from_artists = liked_songs[liked_songs['artist'].isin(new_band_list)]\
    .assign(display_name = lambda x: x['artist'] +  '-' + x['track'])\
        .sort_values(by = 'added_at', ascending = False)\
            .drop_duplicates(subset = 'display_name', keep = 'first')
    playlist_id = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                 select = 'playlist_id',
                                 eq_col_name = 'id',
                                 eq_value = subscription_id).iloc[0]['playlist_id']
    name, description = name_playlist(playlist_type =  'LikedSongsMultiBands',
                                      band_list = new_band_list)
    update_supabase_rows(table_name = 'PlaylistSubscriptions',
                            match_column = 'id',
                            match_column_value = subscription_id,
                            new_row = {'param_list': '|'.join(new_band_list), 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat(), 'description': [user_name + ': ' + name]})
    sp.playlist_change_details(playlist_id = playlist_id, name = name, description = description)
    update_playlist(subscription_id = subscription_id,
                    new_songs = liked_songs_from_artists['uri'],
                    sp = sp,
                    remove = True)

def update_subscription_playlist_publicity(subscription_id, new_playlist_publicity):
    update_supabase_rows(table_name = 'PlaylistSubscriptions',
                            match_column = 'id',
                            match_column_value = subscription_id,
                            new_row = {'public': new_playlist_publicity, 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})

def deactivate_subscription(subscription_id, unfollow = True):
    playlist_id = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                     select = 'playlist_id',
                                     eq_col_name = 'id',
                                     eq_value = subscription_id).iloc[0]['playlist_id']
    if unfollow:
        sp.current_user_unfollow_playlist(playlist_id)
    update_supabase_rows(table_name = 'PlaylistSubscriptions',
                         match_column = 'id',
                         match_column_value = subscription_id,
                         new_row = {'Active': False, 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})

def reactivate_subscription(subscription_id):
    try:
        res = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                 select = 'playlist_id',
                                 eq_col_name = 'id',
                                 eq_value = subscription_id).iloc[0]
        playlist_id = res['playlist_id']
        sp.current_user_follow_playlist(playlist_id)
        followed_playlists = get_followed_playlists(sp)
        if playlist_id in followed_playlists['id']:
            print('Successfully re-followed playlist')
        else:
            print('Error refollowing playlist')
        update_supabase_rows(table_name = 'PlaylistSubscriptions',
                            match_column = 'id',
                            match_column_value = subscription_id,
                            new_row = {'Active': True, 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
    except Exception as e:
        print(f"Error reactivating subscription: {e}")
    
#%%

#%%
#combined playlist:

# user_id = sp.current_user()['id']

# playlist_options = get_owned_or_collaborated_playlists(sp)

# playlist_info_df = pd.DataFrame()
# counter = 0
# for p in playlist_options:
#     playlist_info = sp.playlist(p)
#     playlist_name = playlist_info['name']
#     playlist_info_df = pd.concat([playlist_info_df, pd.DataFrame({'playlist_id': [p],
#                                                      'playlist_name': [playlist_name]})])
#     counter += 1
#     if counter%10 == 0:
#         time.sleep(5)

# playlist_names_to_combine = ['2026 albums', '2026']
# playlist_ids_to_combine = playlist_info_df[playlist_info_df['playlist_name'].str.strip().isin(playlist_names_to_combine)]['playlist_id']

# add_new_playlist(playlist_type = 'CombinePlaylists', public = True,
#                   user_id = user_id, combine_playlist_ids = playlist_ids_to_combine.tolist(),
#                   refresh = 'hourly')


#do this later:
# sp.playlist_upload_cover_image

#go back and add a function to get readable playlists, by trying to pull one song from each playlist and seeing if it errors out.






#%%

