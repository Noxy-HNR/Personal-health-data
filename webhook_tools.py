"""Oura webhook receiver and subscription helpers.

The receiver is local-only by default. Put a secure HTTPS tunnel/reverse proxy in
front of /oura-webhook when registering it with Oura.
"""
from __future__ import annotations
import hashlib, hmac, json, os, secrets, threading, time
from pathlib import Path
from typing import Any
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

BASE_DIR=Path(__file__).resolve().parent
STATE_FILE=BASE_DIR/'data'/'webhook_config.json'
CLIENT_ID=os.getenv('OURA_CLIENT_ID','').strip()
CLIENT_SECRET=os.getenv('OURA_CLIENT_SECRET','').strip()
WEBHOOK_URL=os.getenv('OURA_WEBHOOK_URL','').strip()
API='https://api.ouraring.com/v2/webhook/subscription'

DATA_TYPES=['daily_activity','daily_sleep','daily_readiness','daily_stress','daily_resilience','daily_spo2','daily_cardiovascular_age','vO2_max','sleep','sleep_time','heartrate','workout','session','tag','enhanced_tag','rest_mode_period','ring_battery_level','ring_configuration']
EVENT_TYPES=['create','update','delete']

def _cfg()->dict[str,Any]:
    if STATE_FILE.exists():
        try:return json.loads(STATE_FILE.read_text())
        except Exception:return {}
    return {}

def _save(v):
    STATE_FILE.parent.mkdir(parents=True,exist_ok=True); STATE_FILE.write_text(json.dumps(v,indent=2))

def register_webhook_tools(mcp):
    @mcp.custom_route('/oura-webhook',methods=['GET'])
    async def verify(request:Request):
        cfg=_cfg(); token=request.query_params.get('verification_token',''); challenge=request.query_params.get('challenge','')
        expected=cfg.get('verification_token','')
        if not expected or not challenge or not hmac.compare_digest(token,expected): return JSONResponse({'error':'invalid verification token'},status_code=401)
        return JSONResponse({'challenge':challenge})

    @mcp.custom_route('/oura-webhook',methods=['POST'])
    async def receive(request:Request):
        body=await request.body(); signature=request.headers.get('x-oura-signature',''); timestamp=request.headers.get('x-oura-timestamp','')
        if not signature or not timestamp or not CLIENT_SECRET:return JSONResponse({'error':'webhook authentication unavailable'},status_code=401)
        # Oura signs timestamp + exact JSON body bytes. Recreate the documented HMAC.
        digest=hmac.new(CLIENT_SECRET.encode(),timestamp.encode()+body,hashlib.sha256).hexdigest().upper()
        if not hmac.compare_digest(digest,signature):return JSONResponse({'error':'invalid signature'},status_code=401)
        try:event=json.loads(body)
        except Exception:return JSONResponse({'error':'invalid json'},status_code=400)
        event['_received_at']=time.time()
        cfg=_cfg(); cfg.setdefault('events',[]).append(event); cfg['events']=cfg['events'][-1000:]; _save(cfg)
        # A background worker can consume this event and fetch object_id. We acknowledge
        # immediately to meet Oura's webhook timeout requirement.
        threading.Thread(target=_process_event,args=(event,),daemon=True).start()
        return JSONResponse({'ok':True})

    @mcp.tool()
    def webhook_status()->dict[str,Any]:
        """Show local webhook configuration and recent delivery count without secrets."""
        c=_cfg(); return {'configured':bool(WEBHOOK_URL),'public_url':WEBHOOK_URL or None,'endpoint':'/oura-webhook','recent_events':len(c.get('events',[])),'subscriptions':c.get('subscriptions',[])}

    @mcp.tool()
    def prepare_webhook()->dict[str,Any]:
        """Generate a strong Oura webhook verification token and save it locally."""
        token=secrets.token_urlsafe(32); c=_cfg(); c['verification_token']=token; _save(c)
        return {'verification_token':token,'callback_url':WEBHOOK_URL+'/oura-webhook' if WEBHOOK_URL else None,'next':'Set OURA_WEBHOOK_URL to your public HTTPS base URL, then create subscriptions from the Oura developer console or create_webhook_subscriptions.'}

    @mcp.tool()
    def create_webhook_subscriptions(callback_url:str|None=None, data_types:str='daily_activity,daily_sleep,daily_readiness,daily_stress,daily_resilience,daily_spo2,daily_cardiovascular_age,vO2_max,sleep,sleep_time,heartrate,workout,session,tag,enhanced_tag,rest_mode_period', event_type:str='update')->dict[str,Any]:
        """Create Oura webhook subscriptions for selected data types. Oura verifies the callback during creation."""
        c=_cfg(); token=c.get('verification_token') or prepare_webhook()['verification_token']; url=(callback_url or WEBHOOK_URL).rstrip('/')+'/oura-webhook'
        if not url.startswith('https://'): raise ValueError('Oura webhook callback must be public HTTPS')
        results=[]
        for dt in [x.strip() for x in data_types.split(',') if x.strip()]:
            if dt not in DATA_TYPES: continue
            r=httpx.post(API,headers={'x-client-id':CLIENT_ID,'x-client-secret':CLIENT_SECRET},json={'callback_url':url,'verification_token':token,'event_type':event_type,'data_type':dt},timeout=45)
            try:data=r.json()
            except Exception:data={'status_code':r.status_code,'text':r.text[:500]}
            results.append({'data_type':dt,'status_code':r.status_code,'response':data})
        c['subscriptions']=results; c['callback_url']=url; _save(c); return {'callback_url':url,'results':results}

def _process_event(event):
    # Import lazily to avoid circular startup dependencies.
    try:
        from sync_db import sync_webhook_event
        sync_webhook_event(event)
    except Exception:
        pass
