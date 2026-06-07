import base64, datetime, shutil, os, json, pytz, xbmc

from collections import OrderedDict
from resources.lib.base.l1.constants import ADDON_PROFILE, ADDONS_PATH, CONST_DUT_EPG_BASE, CONST_DUT_EPG, PROVIDER_NAME, SESSION_CHUNKSIZE
from resources.lib.base.l2 import settings
from resources.lib.base.l2.log import log
from resources.lib.base.l3.util import check_key, clear_cache, convert_datetime_timezone, encode32, extract_zip, is_file_older_than_x_days, load_file, load_profile, update_prefs, write_file
from resources.lib.base.l4.session import Session
from resources.lib.constants import CONST_MOD_CACHE

def api_download(url, type, headers=None, data=None, json_data=True, return_json=True, allow_redirects=True, auth=None):
    session = Session(cookies_key='cookies')

    if headers:
        session.headers = headers

    if type == "post" and data:
        if json_data:
            resp = session.post(url, json=data, allow_redirects=allow_redirects, auth=auth)
        else:
            resp = session.post(url, data=data, allow_redirects=allow_redirects, auth=auth)
    else:
        resp = getattr(session, type)(url, allow_redirects=allow_redirects, auth=auth)

    if return_json:
        try:
            returned_data = json.loads(resp.json().decode('utf-8'), object_pairs_hook=OrderedDict)
        except:
            try:
                returned_data = resp.json(object_pairs_hook=OrderedDict)
            except:
                returned_data = resp.text
    else:
        returned_data = resp.text

    session.close()

    return { 'code': resp.status_code, 'data': returned_data, 'headers': resp.headers, 'url': resp.url }

def api_get_channels():
    channels_url = '{dut_epg_url}/channels.json'.format(dut_epg_url=CONST_DUT_EPG)
    file = os.path.join("cache", "channels.json")

    if check_key(CONST_MOD_CACHE, 'channels'):
        days = CONST_MOD_CACHE['channels']
    else:
        days = 1

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=days):
        data = load_file(file=file, isJSON=True)
    else:
        download = api_download(url=channels_url, type='get', headers=None, data=None, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

        if code and code == 200 and data:
            write_file(file=file, data=data, isJSON=True)
            update_prefs(profile_id=1, channels=data)
        else:
            return None

        clear_cache()

    data2 = OrderedDict()

    for currow in data:
        row = data[currow]
        data2[currow] = row

    return data2

def _tmobile_headers(profile_settings):
    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.9,nl;q=0.8',
        'Cache-Control': 'no-cache',
        'Content-Type': 'application/json',
        'DNT': '1',
        'Origin': 'https://tv.odido.nl',
        'Pragma': 'no-cache',
        'Referer': 'https://tv.odido.nl/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }

    try:
        headers['X_CSRFToken'] = profile_settings['csrf_token']
    except:
        pass

    return headers

def _tmobile_query_playbill_list(channel_ids, start_time, end_time, profile_settings):
    payload = {
        'needChannel': '0',
        'queryChannel': {
            'channelIDs': channel_ids,
            'isReturnAllMedia': '1',
        },
        'queryPlaybill': {
            'count': '300',
            'endTime': int(end_time),
            'isFillProgram': '1',
            'offset': '0',
            'startTime': int(start_time),
            'type': '0',
        }
    }

    url = 'https://tv.odido.nl/VSP/V3/QueryPlaybillListStcProps?SID=queryPlaybillListStcProps3&DEVICE=PC&DID={devicekey}&from=throughMSAAccess'.format(devicekey=profile_settings['devicekey'])
    download = api_download(url=url, type='post', headers=_tmobile_headers(profile_settings), data=payload, json_data=True, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'channelPlaybills'):
        return None

    return data

def _tmobile_replay_row(programme, channel_id):
    start_ms = int(programme['startTime'])
    end_ms = int(programme['endTime'])

    startT = datetime.datetime.fromtimestamp(int(start_ms // 1000))
    startT = convert_datetime_timezone(startT, "UTC", "Europe/Amsterdam")
    endT = datetime.datetime.fromtimestamp(int(end_ms // 1000))
    endT = convert_datetime_timezone(endT, "UTC", "Europe/Amsterdam")

    description = ''
    if check_key(programme, 'playbillSeries') and check_key(programme['playbillSeries'], 'sitcomName'):
        description = str(programme['playbillSeries']['sitcomName']).strip()

    if not description and check_key(programme, 'genres'):
        genres = []
        for genre in programme['genres']:
            if check_key(genre, 'genreName'):
                genres.append(str(genre['genreName']))
        description = ', '.join(genres)

    icon = ''
    if check_key(programme, 'picture') and check_key(programme['picture'], 'posters') and len(programme['picture']['posters']) > 0:
        icon = str(programme['picture']['posters'][0])

    row = OrderedDict()
    row['title'] = str(programme['name'])
    row['description'] = description
    row['icon'] = icon
    row['channel'] = str(channel_id)
    row['start'] = int((startT - datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds())
    row['end'] = int((endT - datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds())
    row['program_id'] = str(programme['ID'])
    row['playbill_series'] = programme.get('playbillSeries', {})
    row['genres'] = programme.get('genres', [])

    return row

def _tmobile_cache_replay_result(file, data):
    write_file(file=file, data=data, isJSON=True)
    return data

def api_get_epg_by_date_channel(date, channel):
    if PROVIDER_NAME == 'tmobile':
        file = os.path.join("cache", "{type}.json".format(type=encode32(txt='{date}_{channel}'.format(date=date, channel=channel))))
        marker = os.path.join(ADDON_PROFILE, file)

        if not is_file_older_than_x_days(file=marker, days=0.5):
            return load_file(file=file, isJSON=True)

        profile_settings = load_profile(profile_id=1)
        if not profile_settings or not check_key(profile_settings, 'devicekey') or not check_key(profile_settings, 'csrf_token'):
            return None

        try:
            dt = datetime.datetime.strptime(str(date), '%Y%m%d')
        except:
            return None

        start_date = convert_datetime_timezone(datetime.datetime(dt.year, dt.month, dt.day, 0, 0, 0), "Europe/Amsterdam", "UTC")
        end_date = convert_datetime_timezone(datetime.datetime(dt.year, dt.month, dt.day, 23, 59, 59), "Europe/Amsterdam", "UTC")
        start_time = int((start_date - datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
        end_time = int((end_date - datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000

        data = _tmobile_query_playbill_list([str(channel)], start_time, end_time, profile_settings)
        if not data:
            return None

        data2 = OrderedDict()
        item_count = 0

        for row_group in data['channelPlaybills']:
            if not check_key(row_group, 'playbillLites'):
                continue

            for programme in row_group['playbillLites']:
                if not check_key(programme, 'ID') or not check_key(programme, 'channelID') or not check_key(programme, 'startTime') or not check_key(programme, 'endTime') or not check_key(programme, 'name'):
                    continue

                row = _tmobile_replay_row(programme, channel_id=programme['channelID'])
                if not row:
                    continue

                if row['channel'] != str(channel):
                    continue

                data2[str(item_count)] = row
                item_count += 1

        return _tmobile_cache_replay_result(file=file, data=data2)

    type = '{date}_{channel}'.format(date=date, channel=channel)

    if check_key(CONST_MOD_CACHE, str(type)):
        days = CONST_MOD_CACHE[str(type)]
    else:
        days = 0.5

    type = encode32(txt=type)

    epg_url = '{dut_epg_url}/{type}.json'.format(dut_epg_url=CONST_DUT_EPG, type=type)
    file = os.path.join("cache", "{type}.json".format(type=type))

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=days):
        data = load_file(file=file, isJSON=True)
    else:
        download = api_download(url=epg_url, type='get', headers=None, data=None, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

        if code and code == 200 and data:
            write_file(file=file, data=data, isJSON=True)
        else:
            return None

    return data

def api_get_epg_by_idtitle(idtitle, start, end, channels):
    if PROVIDER_NAME == 'tmobile':
        file = os.path.join("cache", "{type}.json".format(type=encode32(txt=str(idtitle))))
        marker = os.path.join(ADDON_PROFILE, file)

        if not is_file_older_than_x_days(file=marker, days=0.5):
            data = load_file(file=file, isJSON=True)
        else:
            profile_settings = load_profile(profile_id=1)
            if not profile_settings or not check_key(profile_settings, 'devicekey') or not check_key(profile_settings, 'csrf_token'):
                return None

            try:
                start_dt = datetime.datetime.fromtimestamp(int(start), tz=pytz.utc)
                end_dt = datetime.datetime.fromtimestamp(int(end), tz=pytz.utc)
            except:
                return None

            start_time = int(start_dt.timestamp()) * 1000
            end_time = int(end_dt.timestamp()) * 1000

            data = _tmobile_query_playbill_list([str(ch) for ch in channels], start_time, end_time, profile_settings)
            if not data:
                return None

            data2 = OrderedDict()
            item_count = 0

            for row_group in data['channelPlaybills']:
                if not check_key(row_group, 'playbillLites'):
                    continue

                for programme in row_group['playbillLites']:
                    if not check_key(programme, 'ID') or not check_key(programme, 'channelID') or not check_key(programme, 'startTime') or not check_key(programme, 'endTime') or not check_key(programme, 'name'):
                        continue

                    if str(programme['name']) != str(idtitle):
                        continue

                    if str(programme['channelID']) not in channels:
                        continue

                    row = _tmobile_replay_row(programme, channel_id=programme['channelID'])
                    if not row:
                        continue

                    try:
                        if int(row['start']) > int(start) or int(row['end']) < int(end):
                            continue
                    except:
                        pass

                    data2[str(item_count)] = row
                    item_count += 1

            return _tmobile_cache_replay_result(file=file, data=data2)

    type = str(idtitle)

    if check_key(CONST_MOD_CACHE, str(type)):
        days = CONST_MOD_CACHE[str(type)]
    else:
        days = 0.5

    type = encode32(txt=type)

    epg_url = '{dut_epg_url}/{type}.json'.format(dut_epg_url=CONST_DUT_EPG, type=type)
    file = os.path.join("cache", "{type}.json".format(type=type))

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=days):
        data = load_file(file=file, isJSON=True)
    else:
        download = api_download(url=epg_url, type='get', headers=None, data=None, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

        if code and code == 200 and data:
            write_file(file=file, data=data, isJSON=True)
        else:
            return None

    data2 = OrderedDict()

    for currow in data:
        row = data[currow]

        try:
            if int(row['start']) > start or int(row['end']) < end:
                continue
        except:
            pass

        if not row['channel'] in channels:
            continue

        data2[currow] = row

    return data2

def api_get_genre_list(type, add=1):
    add = int(add)

    if not os.path.isdir(os.path.join(ADDON_PROFILE, 'tmp')):
        os.makedirs(os.path.join(ADDON_PROFILE, 'tmp'))

    if add == 1:
        type = type + 'genres'      

    type = encode32(txt=type)

    genres_url = '{dut_epg_url}/{type}.json'.format(dut_epg_url=CONST_DUT_EPG, type=type)
    file = os.path.join("cache", "{type}.json".format(type=type))

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=0.5):
        data = load_file(file=file, isJSON=True)
    else:
        download = api_download(url=genres_url, type='get', headers=None, data=None, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

        if code and code == 200 and data:
            write_file(file=file, data=data, isJSON=True)
        else:
            return None

    return data

def api_get_list(start, end, channels, movies=0):
    if not os.path.isdir(os.path.join(ADDON_PROFILE, 'tmp')):
        os.makedirs(os.path.join(ADDON_PROFILE, 'tmp'))

    list_url = '{dut_epg_url}/list.zip'.format(dut_epg_url=CONST_DUT_EPG)
    tmp = os.path.join(ADDON_PROFILE, 'tmp', 'list.zip')
    
    if movies == 1:
        file = os.path.join("cache", "list_movies.json")
    else:
        file = os.path.join("cache", "list.json")

    if check_key(CONST_MOD_CACHE, 'list'):
        days = CONST_MOD_CACHE['list']
    else:
        days = 0.5

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=days):
        data3 = load_file(file=file, isJSON=True)
    else:
        resp = Session().get(list_url, stream=True)

        if resp.status_code != 200:
            resp.close()
            return None

        with open(tmp, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=SESSION_CHUNKSIZE):
                f.write(chunk)

        resp.close()

        if not extract_zip(file=tmp, dest=os.path.join(ADDON_PROFILE, "cache", "")):
            return None
        else:
            data3 = load_file(file=file, isJSON=True)

    data2 = OrderedDict()

    for currow2 in data3:
        data = data3[currow2]

        for currow in data:
            row = data[currow]
            
            try:
                if not int(row['startl']) < start or not int(row['starth']) > end:
                    continue
            except:
                pass

            try:
                found = False

                for station in row['channels']:
                    if station in channels:
                        found = True
                        break

                if found == False:
                    continue
            except:
                pass

            data2[currow] = row

    return data2

def api_get_list_by_first(first, start, end, channels, movies=False):
    if not os.path.isdir(os.path.join(ADDON_PROFILE, 'tmp')):
        os.makedirs(os.path.join(ADDON_PROFILE, 'tmp'))

    list_url = '{dut_epg_url}/list.zip'.format(dut_epg_url=CONST_DUT_EPG)
    tmp = os.path.join(ADDON_PROFILE, 'tmp', 'list.zip')
    
    if movies == True:
        file = os.path.join("cache", "list_movies.json")
    else:
        file = os.path.join("cache", "list.json")

    if check_key(CONST_MOD_CACHE, 'list'):
        days = CONST_MOD_CACHE['list']
    else:
        days = 0.5

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=days):
        data = load_file(file=file, isJSON=True)
    else:
        resp = Session().get(list_url, stream=True)

        if resp.status_code != 200:
            resp.close()
            return None

        with open(tmp, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=SESSION_CHUNKSIZE):
                f.write(chunk)

        resp.close()

        if not extract_zip(file=tmp, dest=os.path.join(ADDON_PROFILE, "cache", "")):
            return None
        else:
            data = load_file(file=file, isJSON=True)

    data2 = OrderedDict()

    try:
        data = data[str(first)]
    except:
        data = []

    for currow in data:
        row = data[currow]

        try:
            if not int(row['startl']) < start or not int(row['starth']) > end:
                continue
        except:
            pass

        try:
            found = False

            for station in row['channels']:
                if station in channels:
                    found = True
                    break

            if found == False:
                continue
        except:
            pass

        data2[currow] = row

    return data2

def api_get_series_nfo():
    type = 'seriesnfo'
    type = encode32(txt=type)

    vod_url = '{dut_epg_url}/{type}.zip'.format(dut_epg_url=CONST_DUT_EPG, type=type)
    file = os.path.join("cache", "{type}.json".format(type=type))
    tmp = os.path.join(ADDON_PROFILE, 'tmp', "{type}.zip".format(type=type))

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=0.45):
        data = load_file(file=file, isJSON=True)
    else:
        resp = Session().get(vod_url, stream=True)

        if resp.status_code != 200:
            resp.close()
            return None

        with open(tmp, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=SESSION_CHUNKSIZE):
                f.write(chunk)

        resp.close()
        extract_zip(file=tmp, dest=os.path.join(ADDON_PROFILE, "cache", ""))

def api_get_vod_by_type(type, character, genre, subscription_filter, menu=0):
    menu = int(menu)

    if not os.path.isdir(os.path.join(ADDON_PROFILE, 'tmp')):
        os.makedirs(os.path.join(ADDON_PROFILE, 'tmp'))

    if check_key(CONST_MOD_CACHE, str(type)):
        days = CONST_MOD_CACHE[str(type)]
    else:
        days = 0.5

    type = encode32(txt=type)

    vod_url = '{dut_epg_url}/{type}.zip'.format(dut_epg_url=CONST_DUT_EPG, type=type)
    file = os.path.join("cache", "{type}.json".format(type=type))
    tmp = os.path.join(ADDON_PROFILE, 'tmp', "{type}.zip".format(type=type))

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=days):
        data = load_file(file=file, isJSON=True)
    else:
        resp = Session().get(vod_url, stream=True)

        if resp.status_code != 200:
            resp.close()
            return None

        with open(tmp, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=SESSION_CHUNKSIZE):
                f.write(chunk)

        resp.close()

        if not extract_zip(file=tmp, dest=os.path.join(ADDON_PROFILE, "cache", "")):
            return None
        else:
            data = load_file(file=file, isJSON=True)

    if menu == 1:
        return data

    data2 = OrderedDict()

    for currow in data:
        row = data[currow]

        id = row['id']
        
        if genre and genre.startswith('C') and genre[1:].isnumeric():
            if not row['vidcollection'] or not genre in row['vidcollection']:
                continue
        elif genre:
            if not row['category'] or not genre in row['category']:
                continue

        if character:
            if not row['first'] == character:
                continue

        if subscription_filter and not int(id) in subscription_filter:
            continue

        data2[currow] = row

    return data2
