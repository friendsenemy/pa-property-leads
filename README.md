# PA Property Leads

Public-record lead generator for **Greene County, Pennsylvania**, built the same way as
[md-property-leads](https://github.com/friendsenemy/md-property-leads) and
[va-property-leads](https://github.com/friendsenemy/va-property-leads): scheduled GitHub
Actions read free public records and commit JSON; a static dashboard on GitHub Pages reads it.
No server, no paid data, no credentials in the repo.

**Dashboard:** https://pagesofpurposellc.com/pa-property-leads/

## Boards
- **Stacked Leads**: every parcel scored by motivation signals (estate notice, upset/judicial tax sale, sheriff sale, unsound/major-repair blight survey, owner is an estate, absentee, old deed) plus gas context.
- **Oil & Gas**: parcels inside producing Marcellus units (wells within 3/4 mile, pad on the parcel, new permits within 1.5 miles), for royalty/mineral buys.
- **Estates, Sheriff Sales, Tax Sales, Parcel Lookup, My Leads** (shared notes, same sheet as the MD tool, ids prefixed `PA:`).

## Sources (all free, public)
| Module | Source |
|---|---|
| `engine/parcels.py` | Greene County ArcGIS (2024 blight survey, 2023 parcel snapshot) + PA DEP statewide parcels |
| `engine/taxclaim.py` | Greene County Tax Claim Bureau upset (OCR) and judicial sale lists |
| `engine/sheriff.py` | Greene County Sheriff sale listings (CountySuite) |
| `engine/estates.py` | Estate notices in The Greene Reports (palegalads.org) |
| `engine/obits.py` | Herald-Standard obituaries RSS, filtered to Greene towns |
| `engine/wells.py` | PA DEP well locations (PASDA), GreenPort monthly production, SSRS permits and well pads |
| `engine/coal.py` | PA DEP mining operations (mined out, active, longwall) |
| `engine/build.py` | Scores and writes `data/board.json`, `data/details.json`, `data/lookup.json` |

## Schedule
- Daily (~6:23 AM ET): tax claim, sheriff, estates, obituaries, rebuild.
- Weekly (Mon ~3:41 AM ET): parcels, coal, wells/production, rebuild.

Not automated (bot-protected or terms): Register of Wills / Recorder of Deeds (SearchIQS), PA Treasury unclaimed property. Look those up by hand.
