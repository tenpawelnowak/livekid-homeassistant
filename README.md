# LiveKid for Home Assistant

Unofficial integration for the LiveKid parent app (app.livekid.com). It polls the same JSON API the web dashboard uses, every 15 minutes.

## Install
Copy `custom_components/livekid` into your HA `config/custom_components/` (or add this repo to HACS as a custom repository), then restart Home Assistant.

## Setup
1. Log in at https://app.livekid.com.
2. Open DevTools → Network and click any request to `pl.api.api-livekid-prod.com`. Under Request Headers, copy the `authorization` value (`Bearer eyJ…`). You can also paste the whole header block.
3. In HA, go to Settings → Devices & services → Add integration → LiveKid, and paste it.

The token is a JWT with no expiry. If LiveKid ever rejects it (password change, account revision), HA shows a re-authentication prompt where you paste a new one.

Each token is tied to one child. For more children, add the integration again with the child switched in the web app.

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

## Dev
`pip install aiohttp && LIVEKID_TOKEN='…' python scripts/smoke.py`

## License
MIT. See [LICENSE](LICENSE).

This is an unofficial project and is not affiliated with or endorsed by LiveKid.
