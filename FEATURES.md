# Features

What the Drone Security Analyst does for a property owner, in plain language.

## Core

- [x] **Watches live or uploaded video.** The same system handles a live dock camera or a video file you upload.
- [x] **Notices activity on site.** A local vision model reads frames continuously and records what it saw, with the time.
- [x] **Keeps an hourly activity log.** Every reading is saved to an hour-keyed JSON file, even when nothing is alarming.
- [x] **Decides alerts carefully.** About 10 seconds of video (never more than 15), plus what was seen, decides "alert or not". Each session can say what to watch for; a blank brief watches for people, vehicles, packages, animals, and hazards.
- [x] **Knows the time and who is lingering.** It alerts on a person or vehicle after hours (22:00–06:00 by default; for uploads, night as seen in the video) and on anyone who stays in view too long (60 s by default).
- [x] **Pops up an alert when it matters.** The browser shows what was seen, where, how severe, and how confident, at once.
- [x] **Saves evidence clips.** Each alert keeps a short clip and a matching JSON file you can seek into. One event makes one clip.
- [x] **Writes periodic summaries.** Every N minutes (chosen at session start: 1, 5, 10 … 60), with timestamps that point to evidence.
- [x] **Ends with a final summary.** When a video or live session ends, the final summary is the last thing it does.
- [x] **Remembers what happened.** Every reading is stored by day, hour, and minute with its classes, location, and any alert. Search by time or class.
- [x] **Speaks in classes.** Exact objects ("man in a black shirt") are rolled up to classes (person, vehicle, animal, package, hazard, …).
- [x] **Shows telemetry.** For each session: which classes were seen, when, how often, how strongly, and a filterable log of every tagged reading.

## Session options

- [x] **Setup form.** Go live or Upload opens a form: what to watch for (with examples), LLM usage yes/no, summary interval, alert write-ups, and advanced analytics.
- [x] **Detailed alert write-ups** (default off). The LLM adds a richer description after each alert. The pop-up never waits for it.
- [x] **Advanced analytics** (default off). The LLM describes people and vehicles in detail (colour, make, clothing), so you can ask "how many times did the blue Ford F150 come by today?" and get each visit.

## Extras

- [x] **Chat over the day.** Find moments by class and time, or ask for hourly and daily summaries, with clips. It checks with you only when it is unsure which classes you mean.
- [x] **Cost.** A Cost button beside Ask shows the session's model requests, tokens, cost at paid prices, and how much of each model's free daily limit is used.
- [x] **Live updates.** Everything arrives as it happens; the page never polls.
- [x] **Works on a phone.** The layout adapts from desktop to phone.

## How you know it works

- [x] The hourly log fills while video plays.
- [x] A quiet window shows no pop-up.
- [x] An alert window shows a pop-up and saves `chunk_*.mp4` + `chunk_*.json` with a usable seek offset.
- [x] With alert write-ups off, the pop-up path makes no LLM call.
- [x] Each summary period gets a summary with evidence timestamps.
- [x] Ending a video or live session triggers the final summary before the session closes.
- [x] Past events can be found by time or object class.
- [x] A person at midnight and a person lingering both raise alerts; a short daytime visit does not.

## Later

- [ ] Open a decision window early when the scene changes (embedding-based triggers)
- [ ] Real drone position and altitude alongside the camera readings
