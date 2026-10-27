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
    return re.sub(r"[^\w]", "", title.lower(), flags=re.UNICODE).replace("_", "") + "-" + str(year)

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

def enrich(movie):
    title, year = str(movie["title"]).strip(), int(movie["year"])
    results = tmdb("search/movie", {"query":title,"include_adult":"false"}).get("results",[])
    hits = [m for m in results if str(m.get("release_date",""))[:4].isdigit() and abs(int(str(m["release_date"])[:4])-year)<=1 and (same(m.get("title",""),title) or same(m.get("original_title",""),title))]
    if not hits:
        print("No exact TMDB match:",title,year)
        return None
    match = max(hits,key=lambda m:(int(str(m.get("release_date",""))[:4])==year,m.get("popularity",0)))
    details = tmdb("movie/"+str(match["id"]),{"append_to_response":"credits"})
    cast = [person.get("name") for person in details.get("credits",{}).get("cast",[])[:6] if person.get("name")]
    info = {
        "tmdb_id":match["id"], "poster":details.get("poster_path","").lstrip("/"),
        "genre":", ".join(g["name"] for g in details.get("genres",[])),
        "runtime":details.get("runtime"), "plot":details.get("overview",""),
        "cast":cast,"tmdb_url":"https://www.themoviedb.org/movie/"+str(match["id"]),
        "tmdb_rating":round(float(details.get("vote_average") or 0),1)
    }
    if OMDB_KEY:
        params = {"apikey":OMDB_KEY,"t":title,"y":year,"type":"movie"}
        if details.get("imdb_id"):
            params = {"apikey":OMDB_KEY,"i":details["imdb_id"]}
        omdb = get("https://www.omdbapi.com/?" + urllib.parse.urlencode(params))
        if omdb.get("Response") == "True" and (not omdb.get("Year") or str(omdb["Year"])[:4]==str(year)):
            if omdb.get("imdbRating") not in (None,"N/A"): info["imdb_rating"] = omdb["imdbRating"]
            if omdb.get("Metascore") not in (None,"N/A"): info["metacritic_score"] = omdb["Metascore"]
            for rating in omdb.get("Ratings",[]):
                if rating.get("Source")=="Rotten Tomatoes":info["rt_score"]=rating["Value"]
    return info

def main():
    if not (TMDB_KEY or TMDB_TOKEN):
        raise SystemExit("Set TMDB_API_KEY or TMDB_READ_ACCESS_TOKEN in GitHub Secrets")
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
        if current.get("poster") and current.get("imdb_rating") and current.get("rt_score") and current.get("metacritic_score"):
            continue
        try:
            found = enrich(movie)
            if found:
                merged = {**found,**{field:value for field,value in current.items() if value not in ("",None,[])}}
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
