# Feature checklist (plain language)

What the Drone Security Analyst should do for a property owner.

---

## Must-have

- [ ] **Watches live or uploaded video** — Same system handles a live dock camera stream or a video file you upload.
- [ ] **Notices people, vehicles, and other activity on-site** — Looks at sampled frames locally (Mirage) and writes what it saw with time.
- [ ] **Keeps an hourly activity log** — Saves Mirage findings every hour as JSON, even when nothing is alarming.
- [ ] **Decides alerts carefully** — Uses a short clip (about 10 seconds, up to 15) plus what Mirage saw to decide: alert or not.
- [ ] **Pops up an alert when it matters** — Web notification shows Mirage’s finding (what / where / confidence). Does not wait on Flash.
- [ ] **Saves evidence clips** — When there is an alert, keeps a short video chunk and a matching JSON file you can seek into.
- [ ] **Writes a 1-hour summary** — Gemini Flash produces an hour summary with proper timestamps that point to evidence.
- [ ] **Ends with a dead-hand summary** — When a video or monitoring phase finishes, Flash runs last and writes a final stamped summary before the system stops that phase.
- [ ] **Remembers what happened** — Search past events by time or object (e.g. “show all truck events”).
- [ ] **Keeps continuous full video off the cloud** — Full stream stays local; only short decision windows and sparse Flash summary calls may use cloud helpers.

---

## Optional (frontend settings)

- [ ] **Detailed alert summaries (Gemini Flash)** — Setting, **default OFF**. When ON, Flash adds a richer alert write-up after an alert; popup still shows Mirage first.

---

## Nice-to-have (bonus)

- [ ] **Follow-up chat** — Ask more about what the system saw after an alert.
- [ ] **Smarter triggers later** — Research: embedding-based event triggers (not required for v1).

---

## How you’ll know it’s working

- [ ] Hourly Mirage JSON log fills while video plays.
- [ ] A non-alert window does **not** show a popup.
- [ ] An alert window shows a web popup with Mirage output.
- [ ] Alert produces paired `chunk_*.mp4` + `chunk_*.json` with a usable seek offset.
- [ ] With detailed-alert setting OFF, no Flash call is required for the popup path.
- [ ] With detailed-alert setting ON, a richer alert summary is stored after the alert.
- [ ] Each clock hour (while running) gets a Flash summary with evidence timestamps.
- [ ] Ending an uploaded video / phase triggers a final Flash dead-hand summary before exit.
- [ ] You can look up past events by time or object type.
