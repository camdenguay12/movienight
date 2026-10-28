#!/usr/bin/env python3
"""Build public movie discovery catalog from TMDB using private Actions credentials."""
import json,os,urllib.request,urllib.parse,datetime,time
from pathlib import Path
key=os.getenv("TMDB_API_KEY") or os.getenv("TMDB_KEY") or ""
token=os.getenv("TMDB_READ_ACCESS_TOKEN") or os.getenv("TMDB_ACCESS_TOKEN") or ""
if not (key or token):
    raise SystemExit("TMDB credential missing; keeping last discovery catalog")
omdb=os.getenv("OMDB_API_KEY") or os.getenv("OMDB_KEY") or ""
previous={}
try:
    previous={str(x["id"]):x for x in json.loads(Path("data/discovery.json").read_text()).get("movies",[])}
except (FileNotFoundError,ValueError,KeyError):pass
genres={}
try:
    params={"language":"en-US"}
    if key:params["api_key"]=key
    headers={"User-Agent":"RamFlixDiscovery/1.0"}
    if token:headers["Authorization"]="Bearer "+token
    with urllib.request.urlopen(urllib.request.Request("https://api.themoviedb.org/3/genre/movie/list?"+urllib.parse.urlencode(params),headers=headers),timeout=25) as response:
        genres={g["id"]:g["name"] for g in json.load(response).get("genres",[])}
except Exception as e:print("Genre lookup failed",e)
items={}
for category in ("popular","top_rated","now_playing"):
    for page in range(1,6):
        params={"language":"en-US","page":page,"include_adult":"false"}
        if key:params["api_key"]=key
        url="https://api.themoviedb.org/3/movie/"+category+"?"+urllib.parse.urlencode(params)
        headers={"User-Agent":"RamFlixDiscovery/1.0"}
        if token:headers["Authorization"]="Bearer "+token
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=25) as resp:data=json.load(resp)
        except Exception as e:
            print("TMDB fetch failed",category,page,str(e));continue
        for m in data.get("results",[]):
            if not m.get("title") or not m.get("release_date") or not m.get("poster_path"):continue
            if float(m.get("vote_average") or 0)<=5:continue
            ident=str(m["id"])
            item=items.setdefault(ident,{"id":ident,"title":m["title"],"year":int(m["release_date"][:4]),"poster":"https://image.tmdb.org/t/p/w500"+m["poster_path"],"overview":m.get("overview",""),"score":round(float(m.get("vote_average",0)),1),"votes":m.get("vote_count",0),"popularity":m.get("popularity",0),"genres":m.get("genre_ids",[]),"categories":[]})
            if category not in item["categories"]:item["categories"].append(category)
            item["genre"]= ", ".join(genres.get(g,"") for g in item["genres"] if g in genres)
            old=previous.get(ident,{})
            for field in ("imdb_rating","rt_score","metacritic_score","runtime"):
                if old.get(field) is not None:item[field]=old[field]
if omdb:
    enriched=0
    for m in items.values():
        if "imdb_rating" in m or "omdb_checked" in previous.get(m["id"],{}):continue
        if enriched>=150:break
        try:
            url="https://www.omdbapi.com/?"+urllib.parse.urlencode({"apikey":omdb,"t":m["title"],"y":m["year"],"type":"movie"})
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"RamFlixDiscovery/1.0"}),timeout=15) as response:rating=json.load(response)
            if rating.get("Response")=="True" and str(rating.get("Year",""))[:4]==str(m["year"]):
                if rating.get("imdbRating") not in ("N/A",None,""):m["imdb_rating"]=rating["imdbRating"]
                if rating.get("Metascore") not in ("N/A",None,""):m["metacritic_score"]=rating["Metascore"]
                if rating.get("Runtime","").split(" ")[0].isdigit():m["runtime"]=int(rating["Runtime"].split(" ")[0])
                for entry in rating.get("Ratings",[]):
                    if entry.get("Source")=="Rotten Tomatoes":m["rt_score"]=entry.get("Value")
            m["omdb_checked"]=True
            enriched+=1
        except Exception as e:print("OMDb lookup failed",m["title"],str(e))
    print("OMDb lookups",enriched)
if not items:raise SystemExit("No TMDB movies retrieved; keeping last catalog")
# Keep the 100 highest-ranked eligible discoveries, prioritizing popularity while
# maintaining representation from all three discovery categories.
eligible=sorted(items.values(),key=lambda m:(float(m.get("popularity") or 0),float(m.get("score") or 0)),reverse=True)
selected=[]
seen=set()
for category in ("popular","top_rated","now_playing"):
    for movie in (m for m in eligible if category in m["categories"]):
        if sum(category in x["categories"] for x in selected)>=20:break
        if movie["id"] not in seen:
            selected.append(movie);seen.add(movie["id"])
for movie in eligible:
    if len(selected)>=100:break
    if movie["id"] not in seen:
        selected.append(movie);seen.add(movie["id"])
selected=selected[:100]
out={"updatedAt":datetime.datetime.now(datetime.timezone.utc).isoformat(),"movies":selected}
path=Path("data/discovery.json");path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")))
print("Wrote",len(selected),"discoverable films rated above 5/10")
