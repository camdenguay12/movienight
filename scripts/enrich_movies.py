#!/usr/bin/env python3
"""Enrich Letterboxd titles with TMDB metadata; requires TMDB_READ_TOKEN GitHub secret."""
import os,json,base64,zlib,urllib.request,urllib.parse,urllib.error,time,difflib,pathlib
root=pathlib.Path(__file__).resolve().parents[1]
token=os.environ["TMDB_READ_TOKEN"]
omdb_key=os.environ.get("OMDB_API_KEY","")
headers={"Authorization":"Bearer "+token,"Accept":"application/json","User-Agent":"MovieNight/1.0"}
def api(path,params=None):
 url="https://api.themoviedb.org/3/"+path
 if params:url+="?"+urllib.parse.urlencode(params)
 for retry in range(4):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=25) as r:return json.load(r)
  except urllib.error.HTTPError as e:
   if e.code==429 or e.code>=500:time.sleep(3*(retry+1));continue
   raise
 raise RuntimeError("TMDB unavailable: "+url)
raw=(root/"data/camden.b64").read_text().strip()
entries=json.loads(zlib.decompress(base64.b64decode(raw)))
output=root/"data/movie-metadata.json"
metadata=json.loads(output.read_text()) if output.exists() else {}
def norm(s):return ''.join(c for c in s.casefold() if c.isalnum())
for i,(title,year,slug,rating) in enumerate(entries):
 key=f"{norm(title)}-{year}"
 if key in metadata:
  if "tmdb_rating" not in metadata[key]:
   try:
    tmdb=api("movie/"+str(metadata[key]["tmdb_id"]))
    metadata[key]["tmdb_rating"]=round(tmdb["vote_average"],1) if tmdb.get("vote_count") else None
   except Exception as e:print("TMDB score error:",title,str(e))
  if omdb_key and ("imdb_rating" not in metadata[key] or "metacritic_score" not in metadata[key]):
   try:
    movie=metadata[key]
    ids=api("movie/"+str(movie["tmdb_id"])+"/external_ids")
    params={"apikey":omdb_key}
    if ids.get("imdb_id"):params["i"]=ids["imdb_id"]
    else:params.update({"t":title,"y":year})
    url="https://www.omdbapi.com/?"+urllib.parse.urlencode(params)
    with urllib.request.urlopen(url,timeout=25) as response:omdb=json.load(response)
    if omdb.get("Response")=="True":
     movie["imdb_rating"]=omdb.get("imdbRating","N/A")
     movie["rt_score"]=next((r["Value"] for r in omdb.get("Ratings",[]) if r["Source"]=="Rotten Tomatoes"),"N/A")
     movie["metacritic_score"]=omdb.get("Metascore","N/A")
    else:print("OMDb unavailable:",title)
   except Exception as e:print("OMDb error:",title,str(e))
   time.sleep(.3)
  if i%10==0:output.write_text(json.dumps(metadata,ensure_ascii=False,separators=(",",":")))
  continue
 try:
  results=api("search/movie",{"query":title,"year":year,"include_adult":"false"}).get("results",[])
  if not results:results=api("search/movie",{"query":title,"include_adult":"false"}).get("results",[])
  candidates=[]
  for m in results:
   y=int((m.get("release_date") or "0000")[:4])
   sim=max(difflib.SequenceMatcher(None,norm(title),norm(m.get(k,""))).ratio() for k in ("title","original_title"))
   if sim>=.75 and abs(y-year)<=1:candidates.append((sim-(abs(y-year)*.07),m))
  if not candidates:print("Unmatched:",title,year);continue
  movie=max(candidates,key=lambda x:x[0])[1]
  details=api("movie/"+str(movie["id"]),{"append_to_response":"credits"})
  metadata[key]={"tmdb_id":movie["id"],"poster":(details.get("poster_path") or "").lstrip("/"),"genre":", ".join(g["name"] for g in details.get("genres",[])[:3]),"runtime":details.get("runtime"),"plot":details.get("overview",""),"cast":[p["name"] for p in details.get("credits",{}).get("cast",[])[:6]],"tmdb_url":"https://www.themoviedb.org/movie/"+str(movie["id"])}
  metadata[key]["tmdb_rating"]=round(details["vote_average"],1) if details.get("vote_count") else None
  print(i+1,title,"matched")
 except Exception as e:print("Error",title,str(e))
 if i%10==0:output.write_text(json.dumps(metadata,ensure_ascii=False,separators=(",",":")))
 time.sleep(.27)
output.write_text(json.dumps(metadata,ensure_ascii=False,separators=(",",":")))
print("Total metadata:",len(metadata))
