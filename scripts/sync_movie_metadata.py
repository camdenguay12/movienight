#!/usr/bin/env python3
"""Refresh shared Movie Night metadata from TMDB + OMDb using GitHub Actions secrets."""
import json, os, re, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "data/movie-metadata.json"
LIVE = "https://script.google.com/macros/s/AKfycbxWucn9COjS9r1B24bkX-rpmLVU5dXCOtqhbuGCrHQ3Zt1So9IcjQwtoo9pMDSJIktj/exec"
TMDB_KEY = os.getenv("TMDB_API_KEY") or os.getenv("TMDB_KEY") or ""
TMDB_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN") or os.getenv("TMDB_ACCESS_TOKEN") or ""
OMDB_KEY = os.getenv("OMDB_API_KEY") or os.getenv("OMDB_KEY") or ""

def get(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent":"MovieNightMetadata/1.0", **(headers or {})})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)

def key(title, year):
    return normalized(title) + "-" + str(year)

def normalized(title):
    title = unicodedata.normalize("NFKD", str(title).casefold())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in title if not unicodedata.combining(c)))

ALIASES = {
    "cache": {"hidden"}, "hidden": {"cache"},
    "seven": {"se7en"}, "se7en": {"seven"},
    "shawshankredemption": {"theshawshankredemption"},
    "theshawshankredemption": {"shawshankredemption"},
    "eternalsunshineofaspotlessmind": {"eternalsunshineofthespotlessmind"},
    "eternalsunshineofthespotlessmind": {"eternalsunshineofaspotlessmind"}
}
def same(a,b):
    x,y = normalized(a),normalized(b)
    return x==y or y in ALIASES.get(x,set()) or x in ALIASES.get(y,set())

def tmdb(path, params=None):
    params = dict(params or {})
    headers = {}
    if TMDB_TOKEN:
        headers["Authorization"] = "Bearer " + TMDB_TOKEN
    elif TMDB_KEY:
        params["api_key"] = TMDB_KEY
    else:
        raise RuntimeError("Missing TMDB_API_KEY or TMDB_READ_ACCESS_TOKEN secret")
    return get("https://api.themoviedb.org/3/" + path + "?" + urllib.parse.urlencode(params), headers)

def omdb_ratings(title, year, imdb_id=None):
    if not OMDB_KEY:
        return {}
    params = {"apikey": OMDB_KEY, "type": "movie"}
    if imdb_id:
        params["i"] = imdb_id
    else:
        params.update({"t": title, "y": year})
    data = get("https://www.omdbapi.com/?" + urllib.parse.urlencode(params))
    if data.get("Response") != "True":
        print("OMDb no match:", title, year, data.get("Error", ""))
        return {}
    if not imdb_id and str(data.get("Year",""))[:4] != str(year):
        print("OMDb year mismatch:", title, year, data.get("Year"))
        return {}
    out = {}
    if data.get("imdbRating") not in (None, "N/A", ""):
        out["imdb_rating"] = data["imdbRating"]
    if data.get("Metascore") not in (None, "N/A", ""):
        out["metacritic_score"] = data["Metascore"]
    for rating in data.get("Ratings", []):
        if rating.get("Source") == "Rotten Tomatoes":
            out["rt_score"] = rating["Value"]
    return out

def enrich(movie):
    title, year = str(movie["title"]).strip(), int(movie["year"])
    info = {}
    imdb_id = str(movie.get("id") or "")
    if not re.fullmatch(r"tt\\d{7,10}", imdb_id):
        imdb_id = None
    if TMDB_KEY or TMDB_TOKEN:
        results = tmdb("search/movie", {"query":title,"include_adult":"false"}).get("results",[])
        hits = [m for m in results if str(m.get("release_date",""))[:4].isdigit() and abs(int(str(m["release_date"])[:4])-year)<=1 and (same(m.get("title",""),title) or same(m.get("original_title",""),title))]
        if hits:
            match = max(hits,key=lambda m:(int(str(m.get("release_date",""))[:4])==year,m.get("popularity",0)))
            details = tmdb("movie/"+str(match["id"]),{"append_to_response":"credits"})
            cast = [person.get("name") for person in details.get("credits",{}).get("cast",[])[:6] if person.get("name")]
            info = {"tmdb_id":match["id"],"poster":(details.get("poster_path") or "").lstrip("/"),"genre":", ".join(g["name"] for g in details.get("genres",[])),"runtime":details.get("runtime"),"plot":details.get("overview",""),"cast":cast,"tmdb_url":"https://www.themoviedb.org/movie/"+str(match["id"]),"tmdb_rating":round(float(details.get("vote_average") or 0),1)}
            imdb_id = details.get("imdb_id") or imdb_id
        else:
            print("TMDB no match; attempting OMDb independently:",title,year)
    if OMDB_KEY:
        try:
            info.update(omdb_ratings(title,year,imdb_id))
            if not any(k in info for k in ("imdb_rating","rt_score","metacritic_score")) and imdb_id:
                info.update(omdb_ratings(title,year))
        except Exception as exc:
            print("OMDb lookup failed:",title,year,str(exc))
    return info or None

def main():
    if not (TMDB_KEY or TMDB_TOKEN or OMDB_KEY):
        raise SystemExit("Set TMDB or OMDB API secrets in GitHub Actions")\n    print("API configuration: TMDB",bool(TMDB_KEY or TMDB_TOKEN),"OMDb",bool(OMDB_KEY))
    state = get(LIVE)
    films = state.get("films",[])
    existing = json.loads(METADATA.read_text(encoding="utf-8"))
    changed = 0
    for movie in films:
        title,year = movie.get("title"),movie.get("year")
        if not str(title or "").strip():
            imdb_id = str(movie.get("id") or movie.get("imdb_id") or "")
            if re.fullmatch(r"tt\d{7,10}", imdb_id):
                try:
                    matches = tmdb("find/" + imdb_id, {"external_source": "imdb_id"}).get("movie_results", [])
                    if matches:
                        hit = matches[0]
                        resolved = hit.get("title") or hit.get("original_title")
                        resolved_year = str(hit.get("release_date") or "")[:4]
                        if resolved and resolved_year.isdigit():
                            k_missing = "imdb-" + imdb_id
                            record = {"title": resolved, "year": int(resolved_year)}
                            if existing.get(k_missing) != record:
                                existing[k_missing] = record
                                changed += 1
                                print("Resolved missing title:", imdb_id, resolved)
                except Exception as exc:
                    print("Title lookup failed:", imdb_id, str(exc))
            continue
        if not str(year).isdigit(): continue
        k = key(title,year)
        current = existing.get(k,{})
        # Existing curated metadata stays intact; missing public ratings or posters are refreshed.
        if current.get("imdb_rating") and current.get("rt_score") and current.get("metacritic_score"):
            continue
        try:
            found = enrich(movie)
            if found:
                merged = {**current, **{field:value for field,value in found.items() if value not in ("",None,[]) and (field not in current or current.get(field) in ("",None,[]) or field in ("imdb_rating","rt_score","metacritic_score","tmdb_rating"))}}
                if merged != current:
                    existing[k] = merged
                    changed += 1
                    print("Updated:",title,year)
        except Exception as exc:
            print("Lookup failed:",title,year,str(exc))
        time.sleep(0.2)
    if changed:
        METADATA.write_text(json.dumps(existing,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("Updated",changed,"movies out of",len(films))

if __name__=="__main__":
    main()
