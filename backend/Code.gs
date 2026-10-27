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
const MEMBERS=['Camden','Miles','John','Jackson','Kaitlyn','Jess','Dave'];

/* PINs are salted SHA-256 hashes in Script Properties, never in GitHub.
   Admin bootstrap: set Script Property MOVIE_NIGHT_ADMIN_SETUP_KEY to a random secret.
   First enrollment for other members is open until claimed; admin can reset PINs. */
function digest_(value){return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,value).map(b=>('0'+(b&255).toString(16)).slice(-2)).join('')}
function prop_(){return PropertiesService.getScriptProperties()}
function pinKey_(m){return 'PIN_'+m.toUpperCase()}
function pinSet_(m){return !!prop_().getProperty(pinKey_(m))}
function checkPin_(m,pin){const record=prop_().getProperty(pinKey_(m));if(!record||!/^[0-9]{4}$/.test(String(pin)))return false;const parts=record.split(':');return digest_(parts[0]+':'+pin)===parts[1]}
function savePin_(m,pin){if(!MEMBERS.includes(m)||!/^[0-9]{4}$/.test(String(pin)))throw Error('PIN must be exactly four digits');const salt=Utilities.getUuid();prop_().setProperty(pinKey_(m),salt+':'+digest_(salt+':'+pin))}
function session_(token){if(!/^[a-f0-9]{64}$/.test(String(token||'')))return '';return CacheService.getScriptCache().get('session_'+token)||''}
function issue_(member){const token=digest_(Utilities.getUuid()+Utilities.getUuid()+Date.now());CacheService.getScriptCache().put('session_'+token,member,21600);return token}
function auth_(x){
 const member=String(x.member||''),pin=String(x.pin||'');
 if(!MEMBERS.includes(member)||!/^[0-9]{4}$/.test(pin))throw Error('Choose a member and enter a four-digit PIN');
 const cache=CacheService.getScriptCache(),failKey='fails_'+member;
 if(Number(cache.get(failKey)||0)>=8)throw Error('Too many attempts. Try again in 15 minutes');
 if(x.action==='register'){
  if(pinSet_(member))throw Error('This profile already has a PIN');
  if(member==='Camden' && (!prop_().getProperty('MOVIE_NIGHT_ADMIN_SETUP_KEY')||String(x.setupKey||'')!==prop_().getProperty('MOVIE_NIGHT_ADMIN_SETUP_KEY')))throw Error('Administrator setup key required');
  savePin_(member,pin);
 }else if(!checkPin_(member,pin)){
  cache.put(failKey,String(Number(cache.get(failKey)||0)+1),900);
  throw Error('Incorrect PIN');
 }
 cache.remove(failKey);
 return {ok:true,member,token:issue_(member)};
}
function authStatus_(){return Object.fromEntries(MEMBERS.map(m=>[m,pinSet_(m)]))}
function authResult_(x){
 const id=String(x.requestId||'');
 if(!/^[a-zA-Z0-9_-]{16,100}$/.test(id))throw Error('Invalid request ID');
 const cache=CacheService.getScriptCache();
 const result=cache.get('auth_'+id);
 if(!result)return {ok:false,pending:true};
 cache.remove('auth_'+id);return JSON.parse(result);
}

function sheet_(name){return SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName(name)}
function rows_(name){const s=sheet_(name);return s.getLastRow()<2?[]:s.getRange(2,1,s.getLastRow()-1,s.getLastColumn()).getValues()}
function state_(){
 const movies=rows_('Movies').filter(r=>r[0]).map(r=>({id:String(r[0]),title:String(r[1]),year:Number(r[2])||'',genre:String(r[3]||''),poster:String(r[4]||''),letterboxd:String(r[9]||''),ratings:{},watchlist:[]}));
 const byId=new Map(movies.map(f=>[f.id,f]));
 rows_('Member Lists').forEach(r=>{const f=byId.get(String(r[0])),m=String(r[1]);if(!f||!MEMBERS.includes(m))return;if(r[2]==='Rated'&&r[3]!==''&&r[3]!==null)f.ratings[m]=Number(r[3]);else if(r[2]==='Watchlist'&&!f.watchlist.includes(m))f.watchlist.push(m)});
 const quotes={};rows_('Member Quotes').forEach(r=>{if(MEMBERS.includes(String(r[0])))quotes[String(r[0])]=String(r[1]||'')});
 const signatures={};const sigSheet=sheet_('Member Signatures');if(sigSheet&&sigSheet.getLastRow()>1)sigSheet.getRange(2,1,sigSheet.getLastRow()-1,2).getValues().forEach(r=>{if(MEMBERS.includes(String(r[0])))signatures[String(r[0])]=String(r[1]||'')});return {films:movies,quotes,signatures,updatedAt:new Date().toISOString()};
}
function doGet(e){
 const x=e?.parameter||{};const data=JSON.stringify(x.authResult?authResult_(x):x.authStatus?{ok:true,registered:authStatus_()}:state_());
 const callback=String(e?.parameter?.callback||'');
 if(callback&&/^[a-zA-Z_$][\w$]*$/.test(callback))return ContentService.createTextOutput(callback+'('+data+');').setMimeType(ContentService.MimeType.JAVASCRIPT);
 return ContentService.createTextOutput(data).setMimeType(ContentService.MimeType.JSON);
}
function doPost(e){
 const lock=LockService.getScriptLock();lock.waitLock(15000);
 try{
  const x=JSON.parse(e.postData.contents||'{}'),now=new Date().toISOString();
  if(x.action==='login'||x.action==='register'){
   let result;try{result=auth_(x)}catch(err){result={ok:false,error:String(err.message||err)}}
   if(!/^[a-zA-Z0-9_-]{16,100}$/.test(String(x.requestId||'')))throw Error('Invalid request ID');
   CacheService.getScriptCache().put('auth_'+x.requestId,JSON.stringify(result),120);
   return ContentService.createTextOutput(JSON.stringify({ok:true})).setMimeType(ContentService.MimeType.JSON);
  }
  const actor=session_(x.token);
  if(!actor)throw Error('Sign in required');
  if(x.member&&x.member!==actor&&actor!=='Camden')throw Error('Cannot edit another member');
  if(x.action==='resetPin'){
   if(actor!=='Camden'||!MEMBERS.includes(x.member))throw Error('Administrator only');
   prop_().deleteProperty(pinKey_(x.member));
  }else if(x.action==='changePin'){
   if(!MEMBERS.includes(x.member)||x.member!==actor&&actor!=='Camden')throw Error('Not permitted');
   if(actor!=='Camden'&&!checkPin_(actor,x.oldPin))throw Error('Current PIN incorrect');
   savePin_(x.member,String(x.newPin||''));
  }else
  if(x.action==='signature'){if(!MEMBERS.includes(x.member)||!x.movieId)throw Error('Invalid signature movie');const movieIds=rows_('Movies').map(r=>String(r[0]));if(!movieIds.includes(String(x.movieId)))throw Error('Movie not found');const lists=rows_('Member Lists');if(!lists.some(r=>String(r[0])===String(x.movieId)&&String(r[1])===x.member&&['Rated','Watchlist'].includes(String(r[2]))))throw Error('Choose a movie from your own list');const book=SpreadsheetApp.openById(SPREADSHEET_ID);const sh=sheet_('Member Signatures')||book.insertSheet('Member Signatures');if(sh.getLastRow()===0)sh.appendRow(['Member','Movie ID','Updated']);const rows=sh.getLastRow()>1?sh.getRange(2,1,sh.getLastRow()-1,3).getValues():[];const i=rows.findIndex(r=>String(r[0])===x.member),row=[x.member,String(x.movieId),now];if(i<0)sh.appendRow(row);else sh.getRange(i+2,1,1,3).setValues([row]);}else if(x.action==='quote'){
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
   if(actor!=='Camden')throw Error('Poster updates require administrator');
   if(!movieId||movieId.length>120||!/^https:\/\/is[0-9]+-ssl\.mzstatic\.com\/image\/thumb\//.test(url)||url.length>1500)throw Error('Invalid poster');
   const s=sheet_('Movies'),rows=rows_('Movies'),i=rows.findIndex(r=>String(r[0])===movieId);
   if(i<0)throw Error('Movie not found');
   if(!String(rows[i][4]||'').trim())s.getRange(i+2,5).setValue(url);
  }else throw Error('Unknown action');
  return ContentService.createTextOutput(JSON.stringify({ok:true})).setMimeType(ContentService.MimeType.JSON);
 }catch(err){return ContentService.createTextOutput(JSON.stringify({ok:false,error:String(err)})).setMimeType(ContentService.MimeType.JSON)}
 finally{lock.releaseLock()}
}