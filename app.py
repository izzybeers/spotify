#%%
import streamlit as st
import pandas as pd
import numpy as np
import importlib
import os
from pathlib import Path
from datetime import datetime, timedelta, date
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from supabase import create_client, Client
from spotify_data_collection import data, liked_songs, sp, sp_alex, read_from_supabase
from spotify_helper_funs import get_song_info, write_to_supabase, get_followed_playlists, filter_liked_songs_to_artist
from playlist_builder import add_new_playlist, update_playlist, update_subscription_refresh_rate, update_subscription_band_list, update_subscription_playlist_publicity, deactivate_subscription, reactivate_subscription, top_n_songs_by_band

st.set_page_config(page_title="Spotify Phase Explorer", layout="wide")
st.title("My Spotify Analysis")



#%%

if st.button('Refresh'):
    import spotify_data_collection
    spotify_data_collection = importlib.reload(spotify_data_collection)
    from spotify_data_collection import data, liked_songs, sp, sp_alex, read_from_supabase

user_options = sorted(set(data['user_name']))
user_selection = st.selectbox(label = 'Choose a User', options = user_options, index = 1)

if user_selection == 'Izzy Beers':
    sp = sp
else:
    sp = sp_alex
user_id = sp.current_user()['id']
user_name = sp.current_user()['display_name']
data = data[data['user_id'] == user_id]

analysis, playlist_builder = st.tabs(['My Analysis', 'Playlist Builder'])

#songs_to_add: list of uri's
#full_data: dataframe with columns artist and track, to be able to match to the metadata info
def display_songs(songs_to_add, track_info):
    st.header("Songs to be added:")
    songs_to_be_added_with_display_info = track_info[track_info['uri'].isin(songs_to_add)][['artist','track']].drop_duplicates()
    for artist in set(songs_to_be_added_with_display_info['artist']):
        st.subheader(artist)
        songs_by_artist = songs_to_be_added_with_display_info[songs_to_be_added_with_display_info['artist']==artist]
        for song in range(len(songs_by_artist)):
            st.write(songs_by_artist.iloc[song]['track'])

with analysis:
    min_date = min(data['listen_date'])

    date_range_col, amount_to_show_column = st.columns(2)
    date_mapping = {
        '1 Month': date.today() - timedelta(days = 30),
        '3 Months': date.today() - timedelta(days = 90),
        '6 Months': date.today() - timedelta(days = 180),
        'YTD': date(date.today().year,1,1),
        '1 Year': date.today() - timedelta(days = 365),
        '3 Years': date.today() - timedelta(days = 365*3),
        'All Time': min_date
    }

    options = [k for k, val in date_mapping.items() if val >= min_date]
    options.append('Custom')


    with date_range_col:
        time_range = st.radio(
            label = 'Time Range',
            options = options,
            horizontal = True
        )
    colstart, colend = st.columns(2)
    if time_range == 'Custom':
        with colstart:
            start_date = st.date_input(label = 'Start Date',
                                        value = max(min_date, (date(2026,1,1))),
                                        min_value = date(min_date.year, min_date.month, min_date.day),
                                        max_value = date.today())

        with colend:
            end_date = st.date_input(label = 'End Date',
                                    value = date.today(),
                                    min_value = start_date,
                                    max_value = date.today())
            
    else:
        start_date = date_mapping.get(time_range)
        end_date = date.today()


    with amount_to_show_column:
        amount_to_show = st.number_input(
            label = 'Amount to Show',
            min_value = 5,
            max_value = 50,
            value = 10,
            step = 5
        )
        
    songs, artists, albums = st.columns(3)

    if start_date is not None and end_date is not None:
        with songs:
            data_subset = data.query('(listen_date <= @end_date) & (listen_date >= @start_date)').\
                            groupby('display_name', as_index = False)\
                                .agg(num_streams = ('master_metadata_track_name', 'size')).\
                                    sort_values('num_streams', ascending = False)\
                                        .rename(columns = {'display_name': 'song'})
            
            st.write("")
            st.write(f"**My Top {min(amount_to_show, len(data_subset))} Songs From {start_date} to {end_date}**")       
            st.write("")
            st.write("")
            st.write("")
            for i in range(min(amount_to_show, len(data_subset))):
                st.write(f"{data_subset['song'].iloc[i]}")
                st.caption(f"*{data_subset['num_streams'].iloc[i]:,} streams*")

        with artists:
            st.write("")
            artist_subset = data.query('(listen_date <= @end_date) & (listen_date >= @start_date)')\
                                    .groupby('master_metadata_album_artist_name', as_index = False)\
                                        .agg(num_streams = ('master_metadata_track_name', 'size'))\
                                            .sort_values('num_streams', ascending = False)\
                                                .rename(columns = {'master_metadata_album_artist_name': 'artist'})
            st.write(f"**My Top {min(amount_to_show, len(artist_subset))} Artists From {start_date} to {end_date}**")
            st.write("")
            st.write("")
            st.write("")
            for i in range(min(amount_to_show, len(artist_subset))):
                st.write(f"{artist_subset['artist'].iloc[i]}")
                st.caption(f"*{artist_subset['num_streams'].iloc[i]:,} streams*")

        with albums:
            album_subset = data.query('(listen_date <= @end_date) & (listen_date >= @start_date)')\
                        .groupby(['master_metadata_album_artist_name', 'master_metadata_album_album_name'], as_index = False).\
                            agg(num_streams = ('master_metadata_track_name', 'size'),
                                num_distinct_songs = ('master_metadata_track_name', 'nunique')).\
                                    query('num_distinct_songs >= 5').\
                                        sort_values('num_streams', ascending = False).\
                                            assign(album = lambda x: x['master_metadata_album_artist_name'] + ' - ' + x['master_metadata_album_album_name'])[['album', 'num_streams']]
            st.write("")
            st.write(f"**My Top {min(amount_to_show, len(album_subset))} Albums From {start_date} to {end_date}**")
            st.caption("*Must listen to at least 5 tracks to qualify*")
            st.write("")
            for i in range(min(amount_to_show, len(album_subset))):
                st.write(f"{album_subset['album'].iloc[i]}")
                st.caption(f"*{album_subset['num_streams'].iloc[i]:,} song streams*")

with playlist_builder:

    playlist_mode = st.radio('What would you like to do?',
                             ['Create a Playlist', 'Edit a Playlist', 'Reactivate a Playlist'],
                                horizontal = True)
    
    if playlist_mode == 'Create a Playlist':
        playlist_choice = st.radio(label = 'What type of playlist would you like to build?',
                                    options = ['Combine Liked Songs From Multiple Bands', 'Combine Playlists'],
                                    horizontal = True)

        public_selection = st.radio(
                        label = 'Public?',
                        options = ['Yes', 'No'],
                        horizontal = True
                    )
        if playlist_choice == 'Combine Liked Songs From Multiple Bands':
            liked_songs_choice = st.radio(label = '', options = ['Defined by Liked Songs', 'Defined by Top Streams'], horizontal = True)
            if liked_songs_choice == 'Defined by Liked Songs':
                artist_choices = liked_songs.groupby('artist', as_index = False).agg(num_songs = ('track', 'nunique')).assign(display = lambda x: x['artist'] + ' (' + x['num_songs'].astype(str) + ' Liked Songs)' )
                top_n_songs = None
                time_range = None
                edit_label = 'Choose between 2 and 5 Artists To Combine Liked Songs'
            else:
                top_n_songs = st.number_input(label = 'Number of Top Songs to Show Per Band',
                                              min_value = 1, max_value = 50, value = 5, step = 1)
                if len(data[data['listen_date'] < date.today() - timedelta(days = 365)]) > 100:
                    time_range_selection = st.radio(label = '', options = ['Top streams over all time', 'Top streams in past year'], horizontal = True)
                else:
                    time_range_selection = 'Top streams over all time'
                if time_range_selection == 'Top streams over all time':
                    data_to_use = data
                else:
                    data_to_use = data[data['listen_date'] >= date.today() - timedelta(days = 365)]
                    st.info('Note: If the resulting playlist has less than 10 songs, the "all-time" option will be used instead.')
                artist_choices = data_to_use.groupby('master_metadata_album_artist_name', as_index = False).agg(num_streams = ('ts','size'), num_songs = ('master_metadata_track_name', 'nunique')).sort_values('num_streams', ascending = False).\
                    query('num_songs >= @top_n_songs')
                artist_choices = artist_choices.assign(display = lambda x: x['master_metadata_album_artist_name'] + ' (' + x['num_streams'].astype(str) + ' Total Streams)' ).sort_values('display')\
                    .rename(columns = {'master_metadata_album_artist_name': 'artist'})
                song_list = data_to_use.rename(columns = {'master_metadata_album_artist_name': 'artist', 
                                                          'master_metadata_track_name': 'track',
                                                          'spotify_track_uri': 'uri'
                                                          })
                edit_label = 'Choose Artists To Combine'
                time_range = 'alltime' if time_range_selection == 'Top streams over all time' else 'year'
            artist_selection = st.multiselect(
                label =  edit_label,
                options = artist_choices['display']
            )
            band_list = artist_choices[artist_choices['display'].isin(artist_selection)]['artist'].tolist()
            if liked_songs_choice == 'Defined by Top Streams':
                songs_to_add = top_n_songs_by_band(song_list, band_list, top_n_songs, time_range)
                display_songs(songs_to_add, song_list)
            else:
                songs_to_add = filter_liked_songs_to_artist(liked_songs, band_list)

            #implement this later:
            # refresh_cadence = st.select(
            #     label = 'Refresh Cadence',
            #     options = ['Hourly', 'Daily']
            # )

            if st.button(label = 'Go'):
                if ((len(artist_selection) > 1) & (len(artist_selection) <= 5)) | (liked_songs_choice == 'Defined by Top Streams'):
                    try:
                        sub_id = add_new_playlist(playlist_type = 'LikedSongsMultiBands' if liked_songs_choice == 'Defined by Liked Songs' else 'TopSongsMultiBands',
                                                public = np.where(public_selection == 'Yes', True, False).tolist(),
                                                user_id = user_id,
                                                user_name = user_name,
                                                band_list = artist_choices[artist_choices['display'].isin(artist_selection)]['artist'].tolist(),
                                                n = None if liked_songs_choice == 'Defined by Liked Songs' else top_n_songs,
                                                time_range = time_range,
                                                refresh = 'hourly',
                                                song_list = songs_to_add)
                        if sub_id is not None:
                            st.write("Successfully created playlist.")
                    except Exception as e:
                        st.write(f"There was an error creating playlist: {e}")
                else:
                    st.info('Please choose between 2 and 5 artists.')
        elif playlist_choice == 'Combine Playlists':
            with st.spinner('Loading...'):
                followed_playlists = get_followed_playlists(sp)
            playlist_selections = st.multiselect(
                'Choose between 2 and 5 playlists to combine. You must be an owner or collaborator of all selected playlists.',
                options = sorted(followed_playlists['name'])
            )
            selected_rows = followed_playlists[followed_playlists['name'].isin(playlist_selections)]
            st.write(selected_rows)
            if st.button('Go'):
                if (len(playlist_selections) >= 2) & (len(playlist_selections) <= 5):
                    all_readable = True
                    for f in range(len(selected_rows)):
                        try:
                            get_first_song = sp.playlist_items(playlist_id = selected_rows['id'].iloc[f], limit = 1, offset = 0)
                        except Exception as e:
                            all_readable = False
                            st.write(f"You are not an owner or collaborator on the playlist: {selected_rows['name'].iloc[f]}")
                    if all_readable:
                        try:
                            add_new_playlist(playlist_type = 'CombinePlaylists',
                                             public = True, user_id = user_id, user_name = user_name,
                                             refresh = 'hourly', liked_songs = None, band_list = None, combine_playlists = selected_rows)
                            st.write('Successfully created playlist.')
                        except Exception as e:
                            st.write(f"There was an error creating playlist: {e}")
                    
                    
                else:
                    st.info('You must choose between 2 and 5 playlists')


    elif playlist_mode == 'Edit a Playlist':
        playlists = read_from_supabase(table_name = 'PlaylistSubscriptions', select = '*', eq_col_name = 'Active', eq_value = True, chunk_size = None)
        

        # add a more readable display to the playlist subscriptions table that includes user name and playlist name
        playlist_to_edit_selection = st.selectbox('Choose a Playlist To Edit',
                                    playlists['Description'])
        
        playlist_to_edit_or_deactivate = playlists[playlists['Description'] == playlist_to_edit_selection]
        
        
        if st.toggle(label = 'Edit'):
            action_name = 'Change Band List' if playlist_to_edit_or_deactivate['playlist_type'].iloc[0] != 'CombinePlaylists' else 'Change List of Playlists To Combine'
            action_choice = st.radio('What would you like to do?',
                        options = [action_name, 'Change Refresh Cadence', 'Change Publicity', 'Deactivate Playlist'], horizontal = True)
            if action_choice == 'Deactivate Playlist':
                deactivate_decision = st.radio(label = '', options = ['Delete Playlist', 'Keep Playlist But Stop Refreshing'], horizontal = True)
                if st.button('Deactivate'):
                    try:
                        deactivate_subscription(subscription_id = playlist_to_edit_or_deactivate['id'].iloc[0],
                                                unfollow = True if deactivate_decision == 'Delete Playlist' else False)
                            
                        st.info('Successfully deactivated playlist subscription.')
                    except Exception as e:
                        st.info(f"Error deactivating playlist: {e}")
            elif action_choice == action_name:
                if playlist_to_edit_or_deactivate['playlist_type'].iloc[0] == 'LikedSongsMultiBands':
                    artist_choices = liked_songs.groupby('artist', as_index = False).agg(num_songs = ('track', 'nunique')).assign(display = lambda x: x['artist'] + ' (' + x['num_songs'].astype(str) + ' Liked Songs)' )
                    songs_to_use = liked_songs
                    time_range = None
                    top_n_songs = None
                    artists_already_selected = playlist_to_edit_or_deactivate['param_list'].str.split('|').iloc[0]
                elif playlist_to_edit_or_deactivate['playlist_type'].iloc[0] == 'TopSongsMultiBands':
                    band_list, n, original_time_range = playlist_to_edit_or_deactivate['param_list'].str.split(';').iloc[0]
                    artists_already_selected = band_list.split('|')
                    if len(data[data['listen_date'] < date.today() - timedelta(days = 365)]) > 100:
                        time_range_selection = st.radio(label = '', options = ['Top streams over all time', 'Top streams in past year'], horizontal = True,
                                              index = 0 if time_range == 'alltime' else 1)
                    else:
                        time_range_selection = 'Top streams over all time'
                    if time_range_selection == 'Top streams over all time':
                        data_to_display = data
                    else:
                        data_to_display = data[data['listen_date'] >= date.today() - timedelta(days = 365)]
                        st.info('Note: If the resulting playlist has less than 10 songs, the "all-time" option will be used instead.')
                    top_n_songs = st.number_input(label = 'Number of Top Songs to Show Per Band',
                                                                  min_value = 1, max_value = 50, value = int(n), step = 1)
                    artist_choices = data_to_display.groupby('master_metadata_album_artist_name', as_index = False).agg(num_streams = ('ts','size'), num_songs = ('master_metadata_track_name', 'nunique')).sort_values('num_streams', ascending = False).\
                        query('num_songs >= @top_n_songs')
                    artist_choices = artist_choices.assign(display = lambda x: x['master_metadata_album_artist_name'] + ' (' + x['num_streams'].astype(str) + ' Total Streams)' ).sort_values('display')\
                        .rename(columns = {'master_metadata_album_artist_name': 'artist'})
                    song_list = data.rename(columns = {'master_metadata_album_artist_name': 'artist', 
                                                       'master_metadata_track_name': 'track',
                                                       'spotify_track_uri': 'uri'
                                                       })
                    
                artists_already_selected_display = artist_choices[artist_choices['artist'].isin(artists_already_selected)]['display']
                artist_selection = st.multiselect(
                    'Choose between 2 and 5 Artists To Combine Liked Songs',
                    options = artist_choices['display'],
                    default = artists_already_selected_display
                )
                if len(artist_selection) > 0:
                    if top_n_songs is not None:
                        artists_selected = artist_choices.loc[artist_choices['display'].isin(artist_selection), 'artist']
                        time_range = 'alltime' if time_range_selection == 'Top streams over all time' else 'year'
                        songs_to_use = top_n_songs_by_band(song_list, artists_selected, top_n_songs, time_range)
                        display_songs(songs_to_use, song_list)
                        
            if st.button(label = 'Update'):
                if ((len(set(artist_selection) - set(artists_already_selected_display)) == 0) & (len(set(artists_already_selected_display) - set(artist_selection)) == 0)) | (n != top_n_songs & top_n_songs is not None) | ((time_range != original_time_range) & (time_range is not None)):
                    st.info('You have not made any change to your artist list.')
                elif (len(artist_selection) > 1) & (len(artist_selection) <= 5):
                    try:
                        update_subscription_band_list(subscription_id = playlist_to_edit_or_deactivate['id'].iloc[0],
                                                        user_name = user_name,
                                                        new_band_list = artist_choices[artist_choices['display'].isin(artist_selection)]['artist'].tolist(),
                                                        songs_to_update = songs_to_use,
                                                        liked_songs_playlist = playlist_to_edit_or_deactivate['playlist_type'].iloc[0] == 'LikedSongsMultiBands',
                                                        n = top_n_songs,
                                                        time_range = time_range)
                        st.info('Successfully updated band list.')
                    except Exception as e:
                        st.info(f"Error updating playlist: {e}")
                        
                else:
                    st.info('Please choose between 2 and 5 artists.')

    
    else:
        inactive_playlists = read_from_supabase(table_name = 'PlaylistSubscriptions', select = '*', eq_col_name = 'Active', eq_value = False, chunk_size = None)
        
        if len(inactive_playlists) == 0:
            st.info('There are no deactivated playlists.')
        else:
            playlist_to_reactivate_selection = st.selectbox('Choose a Playlist to Reactivate',
                                                  sorted(inactive_playlists['Description']))
            playlist_to_reactivate = inactive_playlists[inactive_playlists['Description'] == playlist_to_reactivate_selection]

            #fix reactivation so it checks for new liked songs
            if st.button(label = 'Reactivate'):
                try:
                    #subscription_deactivation_time = playlist_to_reactivate.iloc[0]['subscription_updated_at']
                    reactivate_subscription(subscription_id = playlist_to_reactivate['id'].iloc[0])
                    # if playlist_to_reactivate.iloc[0]['playlist_type'] == 'LikedSongsMultiBands':
                    #     new_liked_songs_since_deactivation = liked_songs[(liked_songs['added_at'] >= subscription_deactivation_time) & (liked_songs['artist'].isin(playlist_to_reactivate['param_list'].split('|')))]
                    st.info('Successfully reactivated playlist.')
                except Exception as e:
                    st.info(f"Error reactivating playlist: {e}")


                







#%%


#%%



#%%

total_streams = len(data)

one_year_ago = pd.Timestamp.now().date() - pd.DateOffset(years = 1)
three_months_ago = pd.Timestamp.now().date() - pd.DateOffset(months = 3)

total_streams_past_year = len(data[data['day'] >= one_year_ago])
total_streams_past_3_months = len(data[data['day'] >= three_months_ago])

artist_rankings = data.groupby('master_metadata_album_artist_name', as_index = False).agg(num_streams = ('master_metadata_track_name', 'size'),
                                                                                             num_distinct_songs_atleast_5_streams = ('master_metadata_track_name', lambda x: (x.value_counts() >=5).sum()),
                                                                                            num_streams_past_year = ('day', lambda x: sum(x >= one_year_ago)),
                                                                                             num_streams_past_3_months = ('day', lambda x: sum(x >= three_months_ago))).sort_values('num_streams', ascending = False)

artist_rankings = artist_rankings.assign(pct_streams_alltime = lambda x: x['num_streams']/total_streams,
                                         pct_streams_past_year =  lambda x: x['num_streams_past_year']/total_streams_past_year,
                                         pct_streams_past_3_months =  lambda x: x['num_streams_past_3_months']/total_streams_past_3_months
                                        )


artist_rankings_by_year =  data.query('year <= "2026"').groupby(['master_metadata_album_artist_name', 'year'], as_index = False).agg(num_streams = ('master_metadata_track_name', 'size'))
earliest_year_over_30_streams = artist_rankings_by_year.query('num_streams > 30').groupby('master_metadata_album_artist_name', as_index = False).agg(first_year_over_30_streams = ('year', 'min'))
total_streams_by_year = data.query('year <= "2026"').groupby('year', as_index = False).agg(total_streams_all_artists = ('master_metadata_track_name', 'size'))
artist_rankings_by_year = artist_rankings_by_year.merge(total_streams_by_year, on = 'year', how = 'inner')
artist_rankings_by_year = artist_rankings_by_year.assign(pct_streams_this_year = lambda x: x['num_streams']/x['total_streams_all_artists'],
                                                        rank = lambda x: x.groupby('year')['num_streams'].rank(method = 'average',  ascending = False).astype(int)).drop(columns = ['total_streams_all_artists'])

artist_rankings_by_year_wide = artist_rankings_by_year.pivot(
    index='master_metadata_album_artist_name', 
    columns='year', 
    values=['pct_streams_this_year', 'rank']
)

artist_rankings_by_year_wide.columns = [f"{pct_streams}_{year}" for [pct_streams, year] in artist_rankings_by_year_wide.columns]

artist_rankings_by_year_wide[[col for col in artist_rankings_by_year_wide.columns if 'pct' in col]] = artist_rankings_by_year_wide[[col for col in artist_rankings_by_year_wide.columns if 'pct' in col]].fillna(0)
artist_rankings_by_year_wide = artist_rankings_by_year_wide.reset_index()

artist_rankings = artist_rankings.merge(artist_rankings_by_year_wide, on = 'master_metadata_album_artist_name', how = 'left').merge(earliest_year_over_30_streams, on = 'master_metadata_album_artist_name', how = 'left').assign(num_years_fan = lambda x: pd.Timestamp.now().date().year - x['first_year_over_30_streams'].astype('Int64')).drop(columns = ['first_year_over_30_streams'])

artists_top_10_any_year = artist_rankings_by_year[artist_rankings_by_year['rank'] <= 10]['master_metadata_album_artist_name'].unique()

rank_cols = [col for col in artist_rankings.columns if 'rank' in col]
artist_rankings['num_years_top_10_artist'] = (artist_rankings[rank_cols]<=10).sum(axis = 1)
artist_rankings['num_years_top_25_artist'] = (artist_rankings[rank_cols]<=25).sum(axis = 1)
artist_rankings['num_years_top_50_artist'] = (artist_rankings[rank_cols]<=50).sum(axis = 1)
    
artist_rankings.sort_values('num_streams_past_year', ascending = False).head(20)

#%%

#%%

streams_with_liked_songs = data.merge(liked_songs[['uri','added_at']]\
                                         .rename(columns = {'added_at': 'added_to_liked_songs'}), left_on = 'spotify_track_uri', right_on = 'uri', how='left')

streams_with_liked_songs['ts'] = pd.to_datetime(streams_with_liked_songs['ts'], format='ISO8601', utc=True)
streams_with_liked_songs['added_to_liked_songs'] = pd.to_datetime(streams_with_liked_songs['added_to_liked_songs'], format='ISO8601', utc=True)

song_profiling = streams_with_liked_songs\
.assign(earliest_like = streams_with_liked_songs.groupby('display_name')['added_to_liked_songs'].transform('min'))\
.assign(is_before_like = lambda x: x['ts'] < x['earliest_like'],
        first_stream = pd.to_datetime(streams_with_liked_songs.groupby('display_name')['ts'].transform('min'), format='ISO8601',  utc=True))\
        .assign(within_first_week = lambda x: x['ts'] < x['first_stream'] + timedelta(days = 7),
                within_first_month = lambda x: x['ts'] < x['first_stream'] + timedelta(days = 30))\
.sort_values(['display_name', 'ts'], ascending = True)\
    .groupby(['display_name', 'master_metadata_album_artist_name', 'master_metadata_track_name'], as_index = False)\
          .agg(earliest_like = ('earliest_like', 'min'),
               num_streams = ('ts', 'nunique'),
               first_stream = ('first_stream', 'min'),
               second_stream = ('ts', lambda x: x.iloc[1] if len(x) > 1 else None),
               most_recent_stream = ('ts', 'max'),
               num_streams_before_like = ('is_before_like', 'sum'),
               num_streams_within_first_week = ('within_first_week', 'sum'),
               num_streams_within_first_month = ('within_first_month', 'sum'))\
               .assign(time_to_revisit_after_first = lambda x: (pd.to_datetime(x['second_stream'], format='ISO8601',  utc=True) - pd.to_datetime(x['first_stream'], format='ISO8601',  utc=True) if x['second_stream'] is not None else None)/pd.Timedelta(days = 1))


#user profile:
median_distinct_songs_from_favorite_artists = np.median(artist_rankings[artist_rankings['num_streams'] > 100]['num_distinct_songs_atleast_5_streams'])
songs_with_more_than_20_streams = song_profiling[song_profiling['num_streams'] >= 20]
pct_in_liked = np.mean(songs_with_more_than_20_streams['earliest_like'].notna())


#add time series info for streams:
streams_by_quarter = data.assign(quarter = lambda x: pd.to_datetime(x['ts'], format='ISO8601',  utc=True).dt.to_period('Q').astype(str))\
    .groupby(['display_name', 'quarter'], as_index = False)\
        .agg(num_streams = ('ts', 'nunique'))\
        .pivot(index = 'display_name', columns = 'quarter', values = 'num_streams').reset_index()

streams_by_quarter.columns.name = None

streams_by_quarter[[col for col in streams_by_quarter.columns if 'Q' in col]] = streams_by_quarter[[col for col in streams_by_quarter.columns if 'Q' in col]].fillna(0)


song_profiling = song_profiling.merge(streams_by_quarter, on = 'display_name')

song_profiling.groupby('master_metadata_album_artist_name', as_index = False)\
.agg(revisit_rate = ('time_to_revisit_after_first', lambda x: np.mean(x.notna())),
     avg_time_to_revisit_after_first = ('time_to_revisit_after_first', lambda x: np.mean(x.dropna())))



#%%