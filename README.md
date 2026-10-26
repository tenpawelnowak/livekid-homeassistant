# LiveKid for Home Assistant

Unofficial integration for the LiveKid parent app (app.livekid.com). It polls the same JSON API the web dashboard uses, every 15 minutes.

To poll less often, turn off polling in the integration's system options (Settings → Devices & services → LiveKid → ⋮ → System options) and call `homeassistant.update_entity` on any one LiveKid entity from an automation. One call refreshes all entities of that child.

## Install
Copy `custom_components/livekid` into your HA `config/custom_components/` (or add this repo to HACS as a custom repository), then restart Home Assistant.

## Setup
1. Log in at https://app.livekid.com.
2. Open DevTools → Network and click any request to `pl.api.api-livekid-prod.com`. Under Request Headers, copy the `authorization` value (`Bearer eyJ…`). You can also paste the whole header block.
3. In HA, go to Settings → Devices & services → Add integration → LiveKid, and paste it.

Each token is tied to one child. For more children, add the integration again with the child switched in the web app.

## Token lifetime
LiveKid accepts a token for 24 hours after it was issued. After that, the API answers `401 JWTExpired`. Since 0.2.0 the integration handles this itself:

1. It calls `GET /v1/refresh-jwt` with the expired token, as the web app does.
2. It saves the new token in the config entry and retries the request.

The new token belongs to the same login session, so you only paste a token once. HA asks for a new one only when LiveKid refuses the refresh (`IATExpired` or `JWTInvalid`). This happens after a password change, after you log out of that session, or when LiveKid requires a new login. How long LiveKid allows refreshes before it requires a new login is not known; a session 7 days old still refreshed.

Do not log out in the browser you copied the token from. Logging out may end the session the integration uses. Closing the tab is fine.

## Entities (one device per child)
| Entity | Meaning |
|---|---|
| `sensor.*_presence_today` | present / absent / planned_absence / day_off / not_yet |
| `sensor.*_planned_arrival`, `*_planned_departure` | planned hours for today (`in`/`out`) |
| `sensor.*_drop_off`, `*_pick_up` | actual times, if the school records them |
| `sensor.*_hours_this_month` | presence time this month |
| `sensor.*_days_present_this_month` | with absent / planned counts in attributes |
| `sensor.*_balance` | account balance (PLN) |
| `sensor.*_bill_to_pay`, `*_bill_due_date` | latest bill; categories and payments in attributes |
| `calendar.*_schedule` | planned absences, absences, school closures on weekdays |

## API notes
- Base URL: `https://pl.api.api-livekid-prod.com`, header `Authorization: Bearer <jwt>`. No cookies are used.
- Times (`in`/`out`) are minutes after midnight. Money values are integers in grosze.
- `/v1/workdays/{year}` returns the days **off**.
- Errors come as `{"error": {"type": …, "msg": …}}`. `JWTExpired` means refresh with `GET /v1/refresh-jwt` (returns the new JWT as a JSON string); `IATExpired` and `JWTInvalid` need a new login.
- Cloudflare in front of the API blocks some HTTP client signatures (error 1010); aiohttp is allowed.

## Dev
`pip install aiohttp && LIVEKID_TOKEN='…' python scripts/smoke.py`

## Not supported
- Messages and announcements from the school. The web app has them, but the integration does not read them yet.
- Drop-off and pick-up times when the school does not record them. The sensors then stay empty.

## Changelog
- **0.2.0**: Expired tokens are refreshed automatically (`JWTExpired` → `/v1/refresh-jwt`), so entities no longer go unavailable 24 hours after setup. The re-authentication prompt now appears only when LiveKid requires a new login.
- **0.1.0**: First release.

## License
MIT. See [LICENSE](LICENSE).

This is an unofficial project and is not affiliated with or endorsed by LiveKid.
