# Odido / `plugin.video.tmobile` Work Summary

## Goal

Make `plugin.video.tmobile` work against Odido TV.

## High-level result

- Login works.
- Playback now works.
- The final fix was to make the proxy follow Odido's real redirect chain and reuse the final redirected media base dynamically.
- Buffering and channel-switch instability were fixed in the proxy.
- RTL4/Widevine playback is not fully resolved on this Linux laptop, but the same account/stream works on the phone, so the remaining issue is most likely local Widevine/CDM/runtime-specific rather than the Odido add-on flow itself.

## Important current state

Current playback does not depend on a hardcoded media base anymore.

Current `tmobile`/Odido playback flow:

1. `PlayChannel` still returns an `lb.tvx...` MPD URL
2. the proxy fetches that MPD and follows redirects
3. Odido redirects `lb.tvx... -> rrs02y... -> mag01.../wh...`
4. the proxy stores the final redirected base from `r.url`
5. later `PLTV/...` segment requests reuse that dynamic stored base

This is implemented in:

- [service.dutiptv.proxy/service.py](/home/wouter/code/dut-iptv/service.dutiptv.proxy/service.py)

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
    - `final_url`
    - `stream_base_url`
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
  - stores the final redirected MPD base dynamically and reuses it for later `PLTV/...` requests
  - streams segment responses through with `stream=True` and `iter_content(...)` instead of buffering `r.content`
  - uses a threaded HTTP server so status checks and media requests can run concurrently

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
- the browser gets the usable media path only after following Odido's redirect chain
- Kodi needed the proxy to preserve and reuse that final redirected base dynamically

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

### 5. Redirect chain from browser HAR

The pre-playback HAR showed the actual working flow:

1. `PlayChannel` returns `lb.tvx...`
2. browser requests that MPD on `lb.tvx...`
3. `lb.tvx...` returns `302` to `rrs02y...`
4. `rrs02y...` returns `302` to `mag01.../wh...`
5. browser uses that final `mag01/wh...` base for MPD and segments

That finding replaced the temporary hardcoded `mag01/wh...` workaround with the current dynamic proxy fix.

### 6. Proxy performance and stability

Two additional proxy issues were causing poor playback behavior after the URL problem was fixed:

- segment responses were buffered completely in Python before being written to Kodi
- the proxy server was single-threaded, so active media requests could block `/status` checks and channel switches

Fixes:

- stream Odido segment responses with `stream=True` and `iter_content(...)`
- use `socketserver.ThreadingMixIn` for the local proxy HTTP server

Result:

- buffering became normal
- channel switching stopped tripping the "Proxy is not correctly started" error

## Diagnostics that proved useful

### Kodi / proxy local files

Under:

- `/home/wouter/.kodi/userdata/addon_data/plugin.video.tmobile/`

Useful files:

- `full_url`
- `final_url`
- `stream_base_url`
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

The main functional work is done. Remaining cleanup is mostly diagnostic debt:

- decide which temporary diagnostic files should stay vs be removed
- decide whether `playchannel_response*.json` dumps should remain in `api.py`
- decide whether proxy debug files should remain in normal builds
- decide whether the laptop-specific Widevine investigation should stay in-tree or just be documented as an environment issue

## Recommended next step

If this is going to be kept long-term, trim the extra diagnostics and keep the dynamic redirect handling, streamed segment forwarding, and threaded proxy server as the permanent Odido support path.

For RTL4 and similar DRM channels, treat the remaining crash as a local platform issue first:

1. verify on another Kodi/Linux machine before changing add-on logic again
2. compare local `inputstream.adaptive` / Widevine CDM versions against the working device class
3. only resume add-on-side DRM changes if the same stream also fails on another machine with the same cleaned-up proxy path

## DRM note

RTL4 investigation results so far:

- MPD parsing is clean after the current proxy changes
- `cenc:default_KID` injection is in place for Odido manifests that omit it
- the local license proxy no longer forwards `Host: 127.0.0.1:11189` upstream for `tmobile`
- the remaining crash on this laptop is a native `SIGILL` inside `~/.kodi/cdm/libwidevinecdm.so`
- because playback works on the phone, this is currently best classified as a device/runtime-specific Widevine problem, not a proven Odido integration failure

## Operational note

Whenever `plugin.video.tmobile` or `service.dutiptv.proxy` is changed, Kodi must be fully restarted to reload in-memory add-on code.
