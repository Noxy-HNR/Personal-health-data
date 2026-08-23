"""SQLite synchronization layer for Oura V2 documents."""
from __future__ import annotations
import hashlib, json, sqlite3, threading
from datetime import date,timedelta
from pathlib import Path
from typing import Any
DB=Path(__file__).resolve().parent/'data'/'health.db'
LOCK=threading.Lock()
COLLECTION_MAP={'sleep':'sleep','daily_sleep':'daily_sleep','daily_activity':'daily_activity','daily_readiness':'daily_readiness','daily_stress':'daily_stress','daily_resilience':'daily_resilience','daily_spo2':'daily_spo2','daily_cardiovascular_age':'daily_cardiovascular_age','vO2_max':'vO2_max','sleep_time':'sleep_time','heartrate':'heartrate','workout':'workout','session':'session','tag':'tag','enhanced_tag':'enhanced_tag','rest_mode_period':'rest_mode_period','ring_battery_level':'ring_battery_level','ring_configuration':'ring_configuration','personal_info':'personal_info'}

def conn():
    DB.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB,check_same_thread=False); c.row_factory=sqlite3.Row; return c

def init_db():
    with LOCK:
        c=conn(); c.executescript('''CREATE TABLE IF NOT EXISTS documents(collection TEXT NOT NULL, object_id TEXT NOT NULL, day TEXT, start_time TEXT, end_time TEXT, payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(collection,object_id)); CREATE INDEX IF NOT EXISTS idx_documents_day ON documents(day); CREATE INDEX IF NOT EXISTS idx_documents_collection_day ON documents(collection,day); CREATE TABLE IF NOT EXISTS sync_state(collection TEXT PRIMARY KEY,last_sync TEXT,records INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS webhook_events(event_id TEXT PRIMARY KEY,received_at TEXT,event_type TEXT,data_type TEXT,object_id TEXT,user_id TEXT,payload TEXT);'''); c.commit(); c.close()

def upsert(collection:str,row:dict[str,Any]):
    # Python's built-in hash() is randomized per-process for str/bytes (PYTHONHASHSEED),
    # so it must not be used as a stable dedup key -- it would silently produce a
    # different object_id for the same row on every restart, defeating the upsert
    # and re-inserting duplicates for any row lacking id/document_id/timestamp.
    fallback_id=hashlib.sha256(json.dumps(row,sort_keys=True).encode('utf-8')).hexdigest()
    oid=str(row.get('id') or row.get('document_id') or row.get('timestamp') or fallback_id)
    day=row.get('day'); start=row.get('bedtime_start') or row.get('start_datetime') or row.get('timestamp'); end=row.get('bedtime_end') or row.get('end_datetime')
    c=conn(); c.execute('INSERT INTO documents(collection,object_id,day,start_time,end_time,payload,updated_at) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(collection,object_id) DO UPDATE SET day=excluded.day,start_time=excluded.start_time,end_time=excluded.end_time,payload=excluded.payload,updated_at=CURRENT_TIMESTAMP',(collection,oid,day,start,end,json.dumps(row,separators=(',',':')))); c.commit(); c.close()

def store_rows(collection,rows):
    init_db()
    for row in rows:
        if isinstance(row,dict): upsert(collection,row)

def sync_collection(collection,start_date=None,end_date=None):
    from oura_service import _fetch_collection
    result=_fetch_collection(collection,start_date,end_date,max_records=50000); rows=result.get('data',[]); store_rows(collection,rows)
    c=conn(); c.execute('INSERT INTO sync_state(collection,last_sync,records) VALUES(?,CURRENT_TIMESTAMP,?) ON CONFLICT(collection) DO UPDATE SET last_sync=CURRENT_TIMESTAMP,records=excluded.records',(collection,len(rows))); c.commit(); c.close(); return len(rows)

def initial_sync(days:int=365):
    init_db(); end=date.today(); start=end-timedelta(days=max(1,min(days,3650))-1)
    total=0; failures={}
    for collection in COLLECTION_MAP:
        if collection in ('personal_info','ring_configuration','heartrate','ring_battery_level'): continue
        try: total+=sync_collection(collection,start.isoformat(),end.isoformat())
        except Exception as e: failures[collection]=f'{type(e).__name__}: {e}'
    return {'records':total,'failures':failures,'database':str(DB)}

def sync_webhook_event(event):
    init_db(); oid=str(event.get('object_id','')); dt=str(event.get('data_type','')); eid=f"{event.get('event_time','')}:{dt}:{oid}:{event.get('event_type','')}"
    c=conn(); c.execute('INSERT OR IGNORE INTO webhook_events(event_id,received_at,event_type,data_type,object_id,user_id,payload) VALUES(?,?,?,?,?,?,?)',(eid,str(event.get('_received_at','')),event.get('event_type'),dt,oid,event.get('user_id'),json.dumps(event))); c.commit(); c.close()
    if event.get('event_type')=='delete':
        c=conn(); c.execute('DELETE FROM documents WHERE collection=? AND object_id=?',(dt,oid)); c.commit(); c.close(); return
    if dt in COLLECTION_MAP and oid:
        try:
            from oura_service import _access_token, API_BASE
            import httpx
            r=httpx.get(f'{API_BASE}/{dt}/{oid}',headers={'Authorization':f'Bearer {_access_token()}'},timeout=30)
            if r.status_code==200: upsert(dt,r.json())
        except Exception: pass

def register_sync_tools(mcp):
    @mcp.tool()
    def initialize_health_database(days:int=365)->dict[str,Any]:
        """Import historical Oura daily data into the local SQLite database. Run once after authorization."""
        return initial_sync(days)
    @mcp.tool()
    def health_database_status()->dict[str,Any]:
        """Return local database statistics and last synchronization times."""
        init_db(); c=conn(); rows=c.execute('SELECT collection,COUNT(*) n,MAX(updated_at) updated FROM documents GROUP BY collection ORDER BY collection').fetchall(); events=c.execute('SELECT COUNT(*) n FROM webhook_events').fetchone()['n']; c.close(); return {'database':str(DB),'collections':[dict(r) for r in rows],'webhook_events':events}
    @mcp.tool()
    def query_health_history(collection:str='daily_readiness',start_date:str|None=None,end_date:str|None=None,limit:int=50)->dict[str,Any]:
        """Query locally cached Oura history without making an Oura API request. Returns FULL
        raw Oura documents, not a summary -- use only when you need actual record-level detail
        (e.g. "what did my sleep record for August 3rd actually contain"). For averages, trends,
        comparisons, or anomalies, use the compact analytics tools (get_health_snapshot,
        find_metric_trends, compare_periods, find_anomalies, etc.) instead; they return small
        aggregates and never raw records. limit is capped at 1000 regardless of what is requested."""
        init_db(); c=conn(); sql='SELECT object_id,day,start_time,end_time,payload,updated_at FROM documents WHERE collection=?'; args=[collection]
        if start_date: sql+=' AND (day>=? OR day IS NULL)'; args.append(start_date)
        if end_date: sql+=' AND (day<=? OR day IS NULL)'; args.append(end_date)
        sql+=' ORDER BY COALESCE(day,start_time) DESC LIMIT ?'; args.append(max(1,min(limit,1000))); rows=c.execute(sql,args).fetchall(); c.close(); return {'collection':collection,'count':len(rows),'data':[dict(r, payload=json.loads(r['payload'])) for r in rows]}
