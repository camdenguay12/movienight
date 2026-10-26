/**
 * Movie Night shared Google Sheets backend.
 * 1. Open Ramsgate Movie Data > Extensions > Apps Script.
 * 2. Replace Code.gs with this file and save.
 * 3. Deploy > New deployment > Web app.
 *    Execute as: Me; Who has access: Anyone.
 * 4. Send the /exec URL to ChatGPT to connect the GitHub Pages frontend.
 *
 * IMPORTANT: "Anyone" allows anyone who discovers the endpoint to edit the club
 * data. This is appropriate only for a low-risk, trusted hobby site; use
 * authenticated user accounts for a private or protected deployment.
 */
const SPREADSHEET_ID='1iAoojtGJXWfdZlKyqEQoYORLLfND6EhSaX-b12gPt_4';
const MEMBERS=['Camden','Miles','John','Jackson','Kaitlyn','Jess'];
function sheet_(name){return SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName(name)}
function rows_(name){const s=sheet_(name);return s.getLastRow()<2?[]:s.getRange(2,1,s.getLastRow()-1,s.getLastColumn()).getValues()}
function state_(){
 const movies=rows_('Movies').filter(r=>r[0]).map(r=>({id:String(r[0]),title:String(r[1]),year:Number(r[2])||'',genre:String(r[3]||''),poster:String(r[4]||''),letterboxd:String(r[9]||''),ratings:{},watchlist:[]}));
 const byId=new Map(movies.map(f=>[f.id,f]));
 rows_('Member Lists').forEach(r=>{const f=byId.get(String(r[0])),m=String(r[1]);if(!f||!MEMBERS.includes(m))return;if(r[2]==='Rated'&&r[3]!==''&&r[3]!==null)f.ratings[m]=Number(r[3]);else if(r[2]==='Watchlist'&&!f.watchlist.includes(m))f.watchlist.push(m)});
 const quotes={};rows_('Member Quotes').forEach(r=>{if(MEMBERS.includes(String(r[0])))quotes[String(r[0])]=String(r[1]||'')});
 return {films:movies,quotes,updatedAt:new Date().toISOString()};
}
function doGet(e){
 const data=JSON.stringify(state_());
 const callback=String(e?.parameter?.callback||'');
 if(callback&&/^[a-zA-Z_$][\w$]*$/.test(callback))return ContentService.createTextOutput(callback+'('+data+');').setMimeType(ContentService.MimeType.JAVASCRIPT);
 return ContentService.createTextOutput(data).setMimeType(ContentService.MimeType.JSON);
}
function doPost(e){
 const lock=LockService.getScriptLock();lock.waitLock(15000);
 try{
  const x=JSON.parse(e.postData.contents||'{}'),now=new Date().toISOString();
  if(x.action==='quote'){
   if(!MEMBERS.includes(x.member)||typeof x.quote!=='string'||x.quote.length>180)throw Error('Invalid quote');
   const s=sheet_('Member Quotes'),rows=rows_('Member Quotes'),i=rows.findIndex(r=>r[0]===x.member),row=[x.member,x.quote,now];
   if(i<0)s.appendRow(row);else s.getRange(i+2,1,1,3).setValues([row]);
  }else if(x.action==='list'){
   if(!MEMBERS.includes(x.member)||typeof x.movieId!=='string'||x.movieId.length>120)throw Error('Invalid member or movie');
   const movies=rows_('Movies'),known=movies.some(r=>String(r[0])===x.movieId);
   if(!known){
    if(!x.movie||x.movie.id!==x.movieId||typeof x.movie.title!=='string'||x.movie.title.length>200)throw Error('Movie not found');
    const f=x.movie;sheet_('Movies').appendRow([f.id,f.title,Number(f.year)||'',String(f.genre||''),String(f.poster||''),'','','','',String(f.letterboxd||'')]);
   }
   const status=String(x.status||'none'),rating=Number(x.rating);
   if(!['Rated','Watchlist','none'].includes(status)||(status==='Rated'&&(!Number.isFinite(rating)||rating<0||rating>10)))throw Error('Invalid status/rating');
   const s=sheet_('Member Lists'),rows=rows_('Member Lists');
   for(let i=rows.length-1;i>=0;i--)if(String(rows[i][0])===x.movieId&&String(rows[i][1])===x.member)s.deleteRow(i+2);
   if(status!=='none')s.appendRow([x.movieId,x.member,status,status==='Rated'?rating:'',now]);
  }else if(x.action==='poster'){
   const movieId=String(x.movieId||''),url=String(x.posterUrl||'');
   if(!movieId||movieId.length>120||!/^https:\/\/is[0-9]+-ssl\.mzstatic\.com\/image\/thumb\//.test(url)||url.length>1500)throw Error('Invalid poster');
   const s=sheet_('Movies'),rows=rows_('Movies'),i=rows.findIndex(r=>String(r[0])===movieId);
   if(i<0)throw Error('Movie not found');
   if(!String(rows[i][4]||'').trim())s.getRange(i+2,5).setValue(url);
  }else throw Error('Unknown action');
  return ContentService.createTextOutput(JSON.stringify({ok:true})).setMimeType(ContentService.MimeType.JSON);
 }catch(err){return ContentService.createTextOutput(JSON.stringify({ok:false,error:String(err)})).setMimeType(ContentService.MimeType.JSON)}
 finally{lock.releaseLock()}
}