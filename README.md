# Doomsday watcher (District)

Pings your phone when Avengers: Doomsday shows for **21 Dec 2026 or later** open on District:

- **PVR Superplex Inorbit:** alerts with times, price and seat status. **MS Infinity Vision 3D**
  shows get a ⭐ and an urgent alert, and 4DX is skipped.
- **All of Hyderabad:** a one-time 🚨 alert the moment *any* cinema opens 21 Dec on District.
  AMB and Allu only sell on BookMyShow, so treat this as your cue to open the BookMyShow app.

It only reads District's public pages. It never signs in, books or pays.

## Option A: run it on GitHub (no Mac needed)

This repo is already set up for it. Keep it **public**: public repos get unlimited free
Actions minutes, while a private one would run out in about a day.

1. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**.
   Name it `NTFY_TOPIC` and paste your ntfy topic as the value. Your topic stays hidden even though the repo is public.
2. Go to **Actions → Doomsday watcher → Run workflow**, pick **test**, and run it. You should get a
   test alert, and the log should list PVR Inorbit's 20 Dec shows. If the log shows errors
   instead, District is blocking GitHub's servers, so use Option B.
3. Run it once more with **watch**. After that the schedule keeps it going on its own:
   each run checks every 4–6 minutes for ~6 hours, and the next run takes over straight away.
   It stops by itself after 31 Dec.

To stop it: **Actions → Doomsday watcher → ⋯ → Disable workflow**.

## Option B: run it on your Mac

### 1. Add your ntfy topic

Open `district_watch.py` in any text editor (right-click → Open With → TextEdit), find
`aman-doomsday-CHANGE-ME-4821` and replace it with the exact topic name you subscribed to in the ntfy app. Save.

### 2. Test it (nothing to install)

In Terminal:

```bash
cd ~/Downloads/doomsday-watcher      # wherever the file is
python3 district_watch.py --test
```

You should get a test alert on your phone, and Terminal should list PVR Inorbit's Doomsday
shows on **20 Dec**. That proves it's reading District correctly.

### 3. Run it

```bash
caffeinate -i python3 district_watch.py
```

- Leave Terminal open. No browser window this time.
- `caffeinate` stops the Mac sleeping. Keep the lid open and the charger in.
- It checks every 4–6 minutes and alerts once per show, so no spam.
- If District can't be read 3 rounds in a row, you get a ⚠️ alert so it never fails silently.
- Press **Ctrl + C** to stop.

## Changing what it watches

At the top of `district_watch.py`:

| Setting | What it does |
|---|---|
| `CINEMAS` | Add another cinema: open it on district.in and paste its link (without `?fromdate=...`) |
| `START_DATE` / `END_DATE` | Date range (21–31 Dec now) |
| `ONLY_PREFERRED = True` | Alert only for Infinity Vision 3D |
| `CITY_WATCH = False` | Turn off the city-wide early warning |

Other Hyderabad cinemas on District with MS Infinity Vision 3D include PVR Next Galleria
(Panjagutta). Add it to `CINEMAS` if you'd consider it.
