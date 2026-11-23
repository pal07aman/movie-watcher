#!/usr/bin/env python3
"""
Avengers: Doomsday watcher for District (district.in), Hyderabad.

Every few minutes it reads District's public showtime pages and pings your phone when:
  1. your chosen cinemas (PVR Inorbit by default) open Doomsday shows for 21 Dec or later, and
  2. ANY Hyderabad cinema opens Doomsday on District for 21 Dec. That's your early warning to
     open the BookMyShow app and check AMB / Allu, which aren't on District.

It only reads pages and alerts you. It never signs in, books or pays.
No browser needed: plain Python 3, nothing to install.

Run:   caffeinate -i python3 district_watch.py
Test:  python3 district_watch.py --test     (sends a test alert and reads 20 Dec)
"""

import argparse
import html as htmllib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# ----------------------------------------------------------------------------
# SETTINGS: edit these
# ----------------------------------------------------------------------------

# On GitHub these come from the repo's secrets; on your Mac, edit the fallback values.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or "aman-doomsday-CHANGE-ME-4821"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or ""   # optional
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or ""       # optional

MOVIE_KEYWORD = "doomsday"
START_DATE = date(2026, 12, 21)
END_DATE = date(2026, 12, 31)

# District cinema pages. Add more by copying a cinema's District link (without ?fromdate=...).
CINEMAS = [
    {"name": "PVR Superplex Inorbit, Cyberabad",
     "url": "https://www.district.in/movies/pvr-superplex-inorbit-luxe-pxl-4dx-cyberabad-CD1022263"},
]

# City-wide early warning: alert once when START_DATE opens anywhere in Hyderabad on District.
CITY_MOVIE_URL = "https://www.district.in/movies/avengers-doomsday-movie-tickets-in-hyderabad-MV176735"
CITY_WATCH = True

PREFERRED_FORMATS = ["infinity vision 3d"]   # gets a star and an urgent alert
EXCLUDED_FORMATS = ["4dx"]                   # ignored completely
ONLY_PREFERRED = False                       # True = alert only for Infinity Vision 3D

CHECK_EVERY_MINUTES = (4, 6)
HEARTBEAT_HOURS = 12

# ----------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "district_state.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
AVAIL = {"SoldOut": "sold out", "LimitedAvailability": "filling fast", "InStock": "available"}


class FetchError(Exception):
    pass


def log(msg):
    print(f"[{datetime.now():%d %b %H:%M:%S}] {msg}", flush=True)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        raise FetchError(f"{type(e).__name__}: {e}")


# ---------------------------- parsing ---------------------------------------

def open_dates(page_html, url):
    """Dates in the cinema's date selector, from links like ...CD1022263?fromdate=2026-12-20."""
    code = re.escape(url.rstrip("/").rsplit("/", 1)[-1])
    found = sorted({m for m in re.findall(code + r"\?fromdate=(\d{4}-\d{2}-\d{2})", page_html)})
    return [date.fromisoformat(d) for d in found]


def screenings(page_html):
    events = []
    for raw in LD_RE.findall(page_html):
        try:
            data = json.loads(htmllib.unescape(raw))
        except Exception:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "ScreeningEvent":
                events.append(item)
    return events


def doomsday_shows(page_html, day):
    """Doomsday screenings on `day` that pass the format filters."""
    shows = []
    for e in screenings(page_html):
        name = e.get("name", "")
        start = e.get("startDate", "")
        if MOVIE_KEYWORD not in name.lower() or not start.startswith(day.isoformat()):
            continue
        m = re.search(r"\(([^)]*)\)\s*$", name)
        fmt = m.group(1) if m else "Standard"
        low = fmt.lower()
        if any(x in low for x in EXCLUDED_FORMATS):
            continue
        preferred = any(p in low for p in PREFERRED_FORMATS)
        if ONLY_PREFERRED and not preferred:
            continue
        offer = e.get("offers") or {}
        avail = str(offer.get("availability", "")).rsplit("/", 1)[-1]
        shows.append({
            "format": fmt,
            "time": datetime.fromisoformat(start).strftime("%I:%M %p").lstrip("0"),
            "theatre": (e.get("location") or {}).get("name", ""),
            "status": AVAIL.get(avail, avail or "unknown"),
            "price": offer.get("price"),
            "preferred": preferred,
        })
    return shows


def describe(shows):
    by_fmt = {}
    for s in shows:
        by_fmt.setdefault((s["preferred"], s["format"]), []).append(s)
    lines = []
    for (pref, fmt), group in sorted(by_fmt.items(), key=lambda kv: not kv[0][0]):
        times = ", ".join(f"{s['time']} ({s['status']})" for s in group)
        price = f" · ₹{group[0]['price']}" if group[0]["price"] else ""
        lines.append(f"{'⭐ ' if pref else ''}{fmt}{price}: {times}")
    return "\n".join(lines)


# ---------------------------- checks ----------------------------------------

def check_cinema(cinema, start=None, end=None):
    start, end = start or START_DATE, end or END_DATE
    base = cinema["url"].split("?")[0].rstrip("/")
    first = fetch(base)
    dates = open_dates(first, base)
    if not dates:
        raise FetchError("couldn't find the date selector (page layout may have changed)")
    found = {}
    for d in [d for d in dates if start <= d <= end]:
        url = f"{base}?fromdate={d.isoformat()}"
        found[d] = {"url": url, "shows": doomsday_shows(fetch(url), d)}
        time.sleep(random.uniform(1, 3))
    return found, max(dates)


def check_city(day):
    url = f"{CITY_MOVIE_URL}?fromdate={day.isoformat()}"
    shows = [s for s in doomsday_shows(fetch(url), day)]
    theatres = sorted({s["theatre"] for s in shows})
    return url, theatres, shows


# ---------------------------- alerts ----------------------------------------

def notify(title, message, url=None, urgent=False, quiet=False):
    sent = False
    if NTFY_TOPIC and "CHANGE-ME" not in NTFY_TOPIC:
        headers = {"Title": title.encode("utf-8").decode("latin-1", "ignore"),
                   "Priority": "1" if quiet else ("5" if urgent else "4"),
                   "Tags": "hourglass" if quiet else "ticket"}
        if url:
            headers["Click"] = url
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode("utf-8"), headers=headers), timeout=20)
            sent = True
        except Exception as e:
            log(f"ntfy failed: {e}")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        body = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"{title}\n\n{message}" + (f"\n\n{url}" if url else ""),
            "disable_notification": "true" if quiet else "false"}).encode()
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                                   data=body, timeout=20)
            sent = True
        except Exception as e:
            log(f"Telegram failed: {e}")
    if sys.platform == "darwin" and not quiet:
        safe = lambda s: s.replace('"', "'").replace("\n", " · ")
        subprocess.run(["osascript", "-e", f'display notification "{safe(message)[:200]}" '
                        f'with title "{safe(title)}" sound name "Glass"'], capture_output=True)
    if not sent and not quiet:
        log("WARNING: no phone notification went out. Set NTFY_TOPIC (or Telegram) at the top of the script.")


# ---------------------------- main ------------------------------------------

def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"alerted": []}


def remember(state, keys):
    state["alerted"] = sorted(set(state.get("alerted", [])) | set(keys))
    STATE_FILE.write_text(json.dumps(state, indent=2))


def run_test():
    notify("✅ District watcher test", "If you can read this on your phone, alerts work.")
    probe = date(2026, 12, 20)
    for c in CINEMAS:
        try:
            res, latest = check_cinema(c, probe, probe)
            shows = res.get(probe, {}).get("shows", [])
            log(f"{c['name']}: latest open date {latest:%a %d %b}\n  20 Dec matches:\n  "
                + (describe(shows).replace("\n", "\n  ") or "(none matching your filters)"))
        except FetchError as e:
            log(f"{c['name']}: {e}")
    if CITY_WATCH:
        try:
            _, theatres, _ = check_city(probe)
            log(f"City-wide, 20 Dec: Doomsday at {len(theatres)} Hyderabad cinemas on District")
        except FetchError as e:
            log(f"City-wide check: {e}")


def run(minutes=0):
    state = load_state()
    deadline = time.time() + minutes * 60 if minutes else None
    fails, last_fail_alert, last_beat = 0, 0.0, time.time()
    if not os.environ.get("GITHUB_ACTIONS"):
        notify("👀 District watcher started",
               f"Watching {', '.join(c['name'] for c in CINEMAS)} + all Hyderabad for "
               f"{START_DATE:%d %b} onwards.", quiet=True)
    while True:
        if date.today() > END_DATE:
            log("past END_DATE, stopping")
            return
        ok = True
        alerted = set(state.get("alerted", []))

        if CITY_WATCH and f"city|{START_DATE}" not in alerted:
            try:
                url, theatres, shows = check_city(START_DATE)
                if theatres:
                    iv = sorted({s["theatre"] for s in shows if s["preferred"]})
                    msg = (f"{len(theatres)} Hyderabad cinemas on District now show Doomsday on "
                           f"{START_DATE:%d %b}. Open BookMyShow now for AMB / Allu.")
                    if iv:
                        msg += "\n⭐ Infinity Vision 3D at: " + ", ".join(iv)
                    log(f"ALERT city-wide: {msg}")
                    notify(f"🚨 {START_DATE:%d %b} Doomsday bookings are opening!", msg, url, urgent=True)
                    remember(state, [f"city|{START_DATE}"])
                else:
                    log(f"City-wide: {START_DATE:%d %b} not open on District yet")
            except FetchError as e:
                ok = False
                log(f"City-wide check failed: {e}")

        for c in CINEMAS:
            try:
                found, latest = check_cinema(c)
                if not found:
                    log(f"{c['name']}: not open yet (latest date {latest:%a %d %b})")
                for d, info in found.items():
                    new = [s for s in info["shows"]
                           if f"{c['name']}|{d}|{s['format']}|{s['time']}" not in alerted]
                    if not info["shows"]:
                        log(f"{c['name']}: {d:%d %b} open, no matching Doomsday shows yet")
                    if not new:
                        continue
                    urgent = any(s["preferred"] and s["status"] != "sold out" for s in new)
                    title = f"🎟️ Doomsday open: {c['name']}, {d:%a %d %b}"
                    msg = describe(new)
                    log(f"ALERT {title}\n{msg}")
                    notify(title, msg, info["url"], urgent=urgent)
                    remember(state, [f"{c['name']}|{d}|{s['format']}|{s['time']}" for s in new])
                    alerted = set(state["alerted"])
            except FetchError as e:
                ok = False
                log(f"{c['name']}: {e}")
            time.sleep(random.uniform(2, 5))

        fails = 0 if ok else fails + 1
        if fails >= 3 and time.time() - last_fail_alert > 3600:
            notify("⚠️ District watcher can't read District",
                   "3 rounds in a row failed. Check your Mac's internet, or check the apps manually for now.")
            last_fail_alert = time.time()
        if HEARTBEAT_HOURS and time.time() - last_beat > HEARTBEAT_HOURS * 3600:
            notify("District watcher still running", "No new shows yet.", quiet=True)
            last_beat = time.time()

        wait = random.uniform(*CHECK_EVERY_MINUTES) * 60
        if deadline and time.time() + wait > deadline:
            log("time slot used up, exiting so the next scheduled run can take over")
            return
        log(f"next check in {wait / 60:.1f} min")
        time.sleep(wait)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", action="store_true", help="send a test alert and read 20 Dec once")
    ap.add_argument("--minutes", type=float, default=0, help="stop after this many minutes (0 = run forever)")
    args = ap.parse_args()
    try:
        run_test() if args.test else run(args.minutes)
    except KeyboardInterrupt:
        log("stopped")
