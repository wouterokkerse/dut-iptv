# Odido / `plugin.video.tmobile` Work Summary

## Goal

Make `plugin.video.tmobile` work against Odido TV.

## High-level result

- Login works.
- Playback was failing because Kodi/proxy segment requests were going to `lb.tvx.prd.tv.odido.nl`, while the working browser player uses `mag01.tvx.prd.tv.odido.nl/wh.../PLTV/...`.
- A temporary forced proxy base was added, and with that the stream now loads.

## Important current state

The current playback success depends on a temporary hardcoded media base in:

- [service.dutiptv.proxy/service.py](/home/wouter/code/dut-iptv/service.dutiptv.proxy/service.py)

Specifically:

- `TMOBILE_FORCED_MEDIA_BASE = 'https://mag01.tvx.prd.tv.odido.nl/wh7f454c46tw3523540977_-1576042956/'`

This is a diagnostic workaround, not a general solution. The `wh...` prefix appears session/path specific and was taken from a working Firefox HAR.

## Files changed

### `plugin.video.tmobile`

- [plugin.video.tmobile/addon.xml](/home/wouter/code/dut-iptv/plugin.video.tmobile/addon.xml)
  - visible add-on name changed to Odido TV
- [plugin.video.tmobile/README.md](/home/wouter/code/dut-iptv/plugin.video.tmobile/README.md)
  - wording updated from T-Mobile to Odido
- [plugin.video.tmobile/resources/language/resource.language.en_gb/strings.po](/home/wouter/code/dut-iptv/plugin.video.tmobile/resources/language/resource.language.en_gb/strings.po)
- [plugin.video.tmobile/resources/language/resource.language.nl_nl/strings.po](/home/wouter/code/dut-iptv/plugin.video.tmobile/resources/language/resource.language.nl_nl/strings.po)
  - visible strings updated to Odido naming
- [plugin.video.tmobile/resources/lib/api.py](/home/wouter/code/dut-iptv/plugin.video.tmobile/resources/lib/api.py)
  - fixed `license` initialization in `api_play_url`
  - fixed `api_vod_seasons(..., use_cache=True)`
  - added temporary diagnostics:
    - `playchannel_response.json`
    - `playchannel_response_url`
    - `playchannel_response_headers.json`
- [plugin.video.tmobile/resources/lib/base/l3/util.py](/home/wouter/code/dut-iptv/plugin.video.tmobile/resources/lib/base/l3/util.py)
  - removed fallback import of vendored Python 2 `zipfile.py`

### `service.dutiptv.proxy`

- [service.dutiptv.proxy/resources/lib/constants.py](/home/wouter/code/dut-iptv/service.dutiptv.proxy/resources/lib/constants.py)
  - Odido `Origin` / `Referer`
  - Chrome-style UA in proxy headers
- [service.dutiptv.proxy/service.py](/home/wouter/code/dut-iptv/service.dutiptv.proxy/service.py)
  - proxy fetches `tmobile` media itself instead of redirecting
  - writes diagnostics:
    - `full_url`
    - `orig.mpd`
    - `after_sly_mpd_parse.mpd`
    - `after_mpd_parse.mpd`
    - `proxy_request_headers`
    - `proxy_prepared_headers`
    - `proxy_error_url`
    - `proxy_error_status`
    - `proxy_error_headers`
    - `proxy_error_body`
  - retries MPD with browser-style params:
    - `hms_devid`
    - `mag_hms`
    - `RTS`
    - `from=14`
    - `_`
  - contains the temporary forced `mag01/wh...` media base

## Key findings

### 1. Login/session

- Kodi add-on login works against Odido.
- `PlayChannel` succeeds and returns:
  - `playURL`
  - `attachedPlayURL`
- Both currently point only to `lb.tvx.prd.tv.odido.nl`.

### 2. Root playback problem

Kodi path before workaround:

- MPD from `lb.tvx.prd.tv.odido.nl`
- segment init requests also from `lb.tvx.prd.tv.odido.nl`
- segment requests returned `403`

Browser HAR:

- working MPD from `mag01.tvx.prd.tv.odido.nl/wh.../PLTV/...`
- working media segments from the same `mag01/wh...` base
- those requests returned `200`

Conclusion:

- the missing piece was not credentials alone
- the main issue was wrong media host/path

### 3. What was ruled out

These were investigated and are not the primary blocker:

- wrong cookies
- missing CSRF token
- wrong Odido `Origin` / `Referer`
- wrong generic UA
- wrong device identity alone

### 4. Firefox identity experiment

A Firefox local-storage identity import was tested:

- `uuid_cookie`
- `AuthResp_VUID`

This was later reverted because it interfered with the browser session and was not required for the current stream-loading workaround.

Current add-on profile was reset back to Kodi-managed device state.

## Diagnostics that proved useful

### Kodi / proxy local files

Under:

- `/home/wouter/.kodi/userdata/addon_data/plugin.video.tmobile/`

Useful files:

- `full_url`
- `orig.mpd`
- `proxy_error_url`
- `proxy_prepared_headers`
- `playchannel_response.json`

### Browser HAR

Useful HAR:

- `/home/wouter/tv.odido.nl_Archive [26-06-06 09-36-13].har`

What it showed:

- browser requests already started on `mag01...`
- no redirect chain from `lb.tvx...` was visible in that capture
- the first captured media requests were already on the correct `mag01/wh...` base

## Remaining technical debt

The current workaround is not robust because:

- `TMOBILE_FORCED_MEDIA_BASE` is hardcoded
- the `wh...` prefix likely changes between sessions or playback contexts

## Recommended next step

Replace the hardcoded `TMOBILE_FORCED_MEDIA_BASE` with a dynamic derivation from a pre-playback browser/bootstrap step, if that step can be identified.

Most likely future work:

1. capture a HAR from before playback starts
2. identify how the web player obtains the `mag01/wh...` base
3. implement that derivation in the add-on/proxy
4. remove the hardcoded forced media base

## Operational note

Whenever `plugin.video.tmobile` or `service.dutiptv.proxy` is changed, Kodi must be fully restarted to reload in-memory add-on code.
