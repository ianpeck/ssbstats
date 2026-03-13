# TODO

## Scheduling Schema

- Create `scheduled_matches` table as the execution queue for the automation runner. (equivalent of Fight table)
- Mirror legacy `Fight` semantics closely so scheduled rows can map directly into canonical `Fight` rows after execution.
- Include match-level fields for booking and runner execution:
  - `scheduled_match_id`
  - `season_id`
  - `month`
  - `week`
  - `brand_id`
  - `match_order`
  - `scheduled_start_at`
  - `location_id`
  - `fight_type_id`
  - `championship_id` nullable
  - `is_contender_match`
  - `status`
  - `fight_id` nullable after completion
  - `notes`
  - `created_at`
  - `updated_at`
- Use fight-level title logic:
  - if `is_contender_match = TRUE` and `championship_id IS NOT NULL`, this is a `#1 contender` match for that championship
  - if `is_contender_match = FALSE` and `championship_id IS NOT NULL`, this is a championship match
  - if `championship_id IS NULL`, this is a non-title match
- Create `scheduled_match_participants` table so each match can support up to 8 fighters and team formats. (equivalent of Result table)
- Include:
  - `scheduled_match_participant_id`
  - `scheduled_match_id`
  - `slot_number`
  - `fighter_name`
  - `team_id` nullable
  - `team_color` nullable
  - `cpu_level`
  - `cpu_level_source` (`manual`, `elo_suggested`)
  - `seed` nullable
  - `defending_indicator`
  - `created_at`
  - `updated_at`
- Use `team_color` because that maps to actual Smash Ultimate team setup.
- Keep `team_id` too so teammates are grouped explicitly in app logic and queries.
- Use participant-level title logic:
  - `defending_indicator = TRUE` means this participant is the current champion entering the fight
  - `defending_indicator` should only be allowed when `championship_id IS NOT NULL`
  - for standard singles title matches, only one participant should have `defending_indicator = TRUE`
  - for future tag-title support, multiple defending participants may be allowed on the same team
- Enforce participant-count limits in app logic based on selected match type.
- Define runner lifecycle statuses:
  - `queued`
  - `claimed`
  - `running`
  - `awaiting_result`
  - `completed`
  - `failed`
  - `cancelled`
- Add indexes for:
  - current queue lookup by `season_id, month, week, brand_id, match_order`
  - runner polling by `status, scheduled_start_at`
  - follow-up lookup by `fight_id`
  - participant lookup by `scheduled_match_id, slot_number`
- Update legacy canonical tables so `Fight.Fight_ID` and `Results.Result_ID` auto-increment on insert instead of relying on app-side `MAX(id) + 1` logic.
- Verify existing load paths and foreign-key/insert assumptions before altering legacy ID behavior.

## CPU Difficulty Suggestions

- Add CPU level storage per scheduled participant.
- Use Elo difference to suggest a CPU level, but allow manual override every time.
- Define a first-pass Elo-to-CPU-level mapping in app/service code.
- Show whether the current CPU level is:
  - `elo_suggested`
  - `manual`
- Add UI controls to:
  - accept suggested CPU level
  - override CPU level manually
  - reset back to suggested value

## Contendership / PPV Support

- Create `contenderships` table so title-shot state is explicit instead of inferred every time from `FightLog`.
- Include:
  - `contendership_id`
  - `championship_id`
  - `brand_id`
  - `fighter_name`
  - `season_id`
  - `month`
  - `earned_from_scheduled_match_id`
  - `earned_from_fight_id`
  - `status` (`active`, `used`, `revoked`, `expired`)
  - `created_at`
  - `updated_at`
- After a completed scheduled match with `is_contender_match = TRUE`, write the winner into `contenderships`.
- Use `CurrentChampions` + `contenderships` to drive projected month-end PPV championship matches.
- Add a reversible PPV confirmation flow in app logic:
  - projected
  - confirmed
  - completed
  - cancelled

## Media / Ingest

- Create `fight_media` table for Twitch/VOD linkage back to completed fights.
- Include:
  - `fight_media_id`
  - `fight_id`
  - `scheduled_match_id` nullable
  - `media_type` (`live`, `vod`, `clip`, `thumbnail`, `screenshot`)
  - `provider`
  - `media_url`
  - `video_id`
  - `clip_id`
  - `start_offset_seconds`
  - `end_offset_seconds`
  - `created_at`
- Decide whether raw OCR/CV payloads stay only in S3 or also get a lightweight DB table later.

## Database User

- Create a new DB user: `ssbstats_write`
- Grant access only to the new write tables used by the admin schedule flow and automation ingest:
  - `scheduled_matches`
  - `scheduled_match_participants`
  - `contenderships`
  - `fight_media`
- Allowed privileges:
  - `SELECT`
  - `INSERT`
  - `UPDATE`
  - `DELETE`
- Do not grant:
  - `DROP`
  - `GRANT OPTION`
  - broad schema admin privileges
- Note: `TRUNCATE` effectively requires `DROP` in MySQL, so use `DELETE` instead if tables ever need clearing.

## AWS / Storage

- Create an S3 bucket for automation artifacts:
  - capture screenshots
  - raw fight/result JSON payloads before canonical DB load
- Partition object keys by league structure:
  - `season=<season>/month=<month>/week=<week>/brand=<brand>/...`
- First-pass object layout:
  - `season=<season>/month=<month>/week=<week>/brand=<brand>/screenshots/<scheduled_match_id>/`
  - `season=<season>/month=<month>/week=<week>/brand=<brand>/raw-json/<scheduled_match_id>/fight.json`
  - `season=<season>/month=<month>/week=<week>/brand=<brand>/raw-json/<scheduled_match_id>/results.json`
- Decide canonical brand values for partitioning:
  - `ult`
  - `melee`
  - `brawl`
- Add bucket security defaults:
  - block public access
  - SSE-S3 encryption enabled
  - lifecycle rule later for debug screenshots if storage grows
- Create IAM credentials/policy limited to:
  - `s3:PutObject`
  - `s3:GetObject`
  - `s3:ListBucket`
  - only for this bucket/prefix set
- Add app/runner env vars for:
  - bucket name
  - AWS region
  - access key / secret or role-based auth

## Hardware / Runner Topology

- Planned hardware/control setup:
  - `ssbstats.app` admin page is the control plane
  - dedicated PC runs the Python automation runner, OBS, Twitch integration, and OpenCV/OCR
  - docked Nintendo Switch 2 is the gameplay target
  - Raspberry Pi Pico 2 W acts as the programmable controller/input layer
  - capture card feeds Switch video into the PC
- Planned control path:
  - `ssbstats.app -> Python runner on PC -> Pico 2 W -> Switch 2`
- Planned video path:
  - `Switch 2 dock HDMI out -> capture card HDMI in -> capture card USB -> PC`
- Optional local display path if passthrough is used:
  - `capture card HDMI out -> TV/monitor`
- Runner responsibilities on the PC:
  - poll scheduled matches from the website
  - send dynamic input commands to the Pico 2 W
  - watch capture-card video for menu/result verification
  - stream to Twitch through OBS
  - upload screenshots/raw JSON to S3
  - load canonical fight/results data back into the database
- Need to finalize the PC-to-Pico 2 W command channel design:
  - serial/UART
  - Wi-Fi/network
  - other control path if testing shows a better option
- Need an early proof-of-life test:
  - PC can issue a command
  - Pico 2 W can translate it into controller input
  - Switch 2 accepts the input reliably
  - PC can simultaneously read the capture feed

## Web App Follow-Up

- Build admin page for current-week scheduling only.
- Split page by the three brands and order matches within each brand.
- Lock `season_id`, `month`, and `week` in the UI to the current active booking window.
- Lock `brand_id` based on the brand section the admin is editing.
- Allow empty scheduled fights to be created and filled in later within the current week.
- Allow text/select entry for fight metadata like location, fight type, championship, contender flag, and notes.
- Allow participant-level entry for fighter, team, team color, CPU level, seed, and defending indicator.
- Support participant-based scheduling instead of fixed fighter 1 / fighter 2 columns.
- Support up to 8 participants per match.
- Support team matches with explicit `team_id` and `team_color`.
- Add per-participant CPU level controls with Elo-based suggested defaults and manual override.
- Add projected PPV section showing month-end championship matches derived from current champions + active contenderships.
- Add confirm / undo-confirm action for projected PPV fights.
- Expose runner-facing API endpoints for:
  - next queued match
  - claim match
  - update status
  - attach final `fight_id`
  - attach Twitch media metadata
