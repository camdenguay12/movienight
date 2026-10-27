#!/usr/bin/env python3
"""Build public movie discovery catalog from TMDB using private Actions credentials."""
import json,os,urllib.request,urllib.parse,datetime
from pathlib import Path
key=os.getenv("TMDB_API_KEY") or os.getenv("TMDB_KEY") or ""
token=os.getenv("TMDB_READ_ACCESS_TOKEN") or os.getenv("TMDB_ACCESS_TOKEN") or ""
if not (key or token):
    raise SystemExit("TMDB credential missing; keeping last discovery catalog")
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
            ident=str(m["id"])
            item=items.setdefault(ident,{"id":ident,"title":m["title"],"year":int(m["release_date"][:4]),"poster":"https://image.tmdb.org/t/p/w500"+m["poster_path"],"overview":m.get("overview",""),"score":round(float(m.get("vote_average",0)),1),"votes":m.get("vote_count",0),"popularity":m.get("popularity",0),"genres":m.get("genre_ids",[]),"categories":[]})
            if category not in item["categories"]:item["categories"].append(category)
if not items:raise SystemExit("No TMDB movies retrieved; keeping last catalog")
out={"updatedAt":datetime.datetime.now(datetime.timezone.utc).isoformat(),"movies":list(items.values())}
path=Path("data/discovery.json");path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")))
print("Wrote",len(items),"discoverable films")
