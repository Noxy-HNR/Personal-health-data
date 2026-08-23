"""Local-first Oura analytics tools.

These tools deliberately do calculations server-side so small/medium local models
receive compact, useful results instead of large raw time-series payloads.
"""
from __future__ import annotations
from datetime import date, timedelta
from math import sqrt
from statistics import mean, median
from typing import Any


def _nums(rows: list[dict[str, Any]], *keys: str) -> list[float]:
    out=[]
    for r in rows:
        v=r
        for k in keys:
            if isinstance(v, dict): v=v.get(k)
            else: v=None
        if isinstance(v,(int,float)):
            out.append(float(v))
    return out


def _pearson(a: list[float], b: list[float]) -> float:
    n=min(len(a),len(b))
    if n<3: return 0.0
    a=a[:n]; b=b[:n]
    ma=mean(a); mb=mean(b)
    da=[x-ma for x in a]; db=[x-mb for x in b]
    den=sqrt(sum(x*x for x in da)*sum(x*x for x in db))
    return sum(x*y for x,y in zip(da,db))/den if den else 0.0


def _trend(values: list[float]) -> dict[str,Any]:
    n=len(values)
    if n<3: return {"direction":"insufficient_data","slope":0,"r_squared":0,"change_percent":0,"n":n}
    x=list(range(n)); mx=mean(x); my=mean(values)
    den=sum((i-mx)**2 for i in x)
    slope=sum((i-mx)*(v-my) for i,v in zip(x,values))/den if den else 0
    ss_tot=sum((v-my)**2 for v in values)
    ss_res=sum((v-(my+slope*(i-mx)))**2 for i,v in zip(x,values))
    r2=1-ss_res/ss_tot if ss_tot else 0
    pct=(values[-1]-values[0])/abs(values[0])*100 if values[0] else 0
    return {"direction":"rising" if slope>0.05 else "falling" if slope<-0.05 else "stable","slope_per_day":round(slope,4),"r_squared":round(max(0,r2),4),"change_percent":round(pct,2),"n":n}


def _iqr(values:list[float])->tuple[float,float]:
    if len(values)<4:return (min(values),max(values))
    s=sorted(values)
    def q(p):
        x=(len(s)-1)*p; i=int(x); f=x-i
        return s[i]+(s[min(i+1,len(s)-1)]-s[i])*f
    q1=q(.25); q3=q(.75); d=q3-q1
    return q1-1.5*d,q3+1.5*d


def register_analytics_tools(mcp):
    @mcp.tool()
    def get_personal_baseline(days:int=30)->dict[str,Any]:
        """Calculate personal baselines for major daily Oura metrics over the requested window."""
        from oura_service import _fetch_collection
        end=date.today(); start=end-timedelta(days=max(1,min(days,365))-1)
        metrics={
          "sleep_score":("daily_sleep","score"),"readiness_score":("daily_readiness","score"),
          "activity_score":("daily_activity","score"),"stress_high":("daily_stress","stress_high"),
          "recovery_index":("daily_readiness","contributors.recovery_index"),
          "temperature_deviation":("daily_readiness","temperature_deviation"),
          "hrv_balance":("daily_readiness","contributors.hrv_balance"),
          "resting_heart_rate":("daily_readiness","contributors.resting_heart_rate"),
        }
        result={"window_days":days,"start_date":start.isoformat(),"end_date":end.isoformat(),"metrics":{}}
        for name,(collection,key) in metrics.items():
            rows=_fetch_collection(collection,start.isoformat(),end.isoformat(),max_records=1000).get("data",[])
            vals=_nums(rows,*key.split('.'))
            if vals:
                lo,hi=_iqr(vals); result["metrics"][name]={"mean":round(mean(vals),2),"median":round(median(vals),2),"min":round(min(vals),2),"max":round(max(vals),2),"iqr_expected_range":[round(lo,2),round(hi,2)],"n":len(vals)}
        return result

    @mcp.tool()
    def find_metric_trends(metric:str="readiness_score",days:int=30)->dict[str,Any]:
        """Find the trend of a major Oura daily metric. Supported metrics: sleep_score, readiness_score, activity_score, stress_high, resting_heart_rate, hrv_balance, recovery_index, temperature_deviation."""
        from oura_service import _fetch_collection
        mapping={"sleep_score":("daily_sleep","score"),"readiness_score":("daily_readiness","score"),"activity_score":("daily_activity","score"),"stress_high":("daily_stress","stress_high"),"resting_heart_rate":("daily_readiness","contributors.resting_heart_rate"),"hrv_balance":("daily_readiness","contributors.hrv_balance"),"recovery_index":("daily_readiness","contributors.recovery_index"),"temperature_deviation":("daily_readiness","temperature_deviation")}
        if metric not in mapping: raise ValueError(f"Unsupported metric. Choose from: {', '.join(mapping)}")
        end=date.today(); start=end-timedelta(days=max(3,min(days,365))-1)
        rows=_fetch_collection(mapping[metric][0],start.isoformat(),end.isoformat(),max_records=2000).get("data",[])
        vals=_nums(rows,*mapping[metric][1].split('.'))
        return {"metric":metric,"period_days":days,"trend":_trend(vals),"baseline":round(mean(vals),2) if vals else None,"recent":round(vals[-1],2) if vals else None}

    @mcp.tool()
    def compare_periods(metric:str="readiness_score",recent_days:int=14,baseline_days:int=30)->dict[str,Any]:
        """Compare a recent Oura metric window against the preceding baseline window."""
        from oura_service import _fetch_collection
        mapping={"sleep_score":("daily_sleep","score"),"readiness_score":("daily_readiness","score"),"activity_score":("daily_activity","score"),"stress_high":("daily_stress","stress_high"),"resting_heart_rate":("daily_readiness","contributors.resting_heart_rate"),"hrv_balance":("daily_readiness","contributors.hrv_balance")}
        if metric not in mapping: raise ValueError("Unsupported metric")
        end=date.today(); recent_start=end-timedelta(days=recent_days-1); base_start=recent_start-timedelta(days=baseline_days)
        rows=_fetch_collection(mapping[metric][0],base_start.isoformat(),end.isoformat(),max_records=3000).get("data",[])
        vals=_nums(rows,*mapping[metric][1].split('.'))
        # Collection ordering is chronological in Oura responses; use last windows conservatively.
        recent=vals[-recent_days:]; baseline=vals[-(recent_days+baseline_days):-recent_days]
        a=mean(recent) if recent else 0; b=mean(baseline) if baseline else 0
        return {"metric":metric,"recent":{"days":len(recent),"mean":round(a,2)},"baseline":{"days":len(baseline),"mean":round(b,2)},"absolute_change":round(a-b,2) if baseline else None,"percent_change":round((a-b)/abs(b)*100,2) if b else None}

    @mcp.tool()
    def find_anomalies(metric:str="readiness_score",days:int=30)->dict[str,Any]:
        """Find unusually high/low daily values using a personal IQR rule."""
        from oura_service import _fetch_collection
        mapping={"sleep_score":("daily_sleep","score"),"readiness_score":("daily_readiness","score"),"activity_score":("daily_activity","score"),"resting_heart_rate":("daily_readiness","contributors.resting_heart_rate"),"hrv_balance":("daily_readiness","contributors.hrv_balance")}
        if metric not in mapping: raise ValueError("Unsupported metric")
        end=date.today(); start=end-timedelta(days=max(7,min(days,365))-1)
        rows=_fetch_collection(mapping[metric][0],start.isoformat(),end.isoformat(),max_records=3000).get("data",[])
        vals=_nums(rows,*mapping[metric][1].split('.')); lo,hi=_iqr(vals) if vals else (0,0)
        return {"metric":metric,"window_days":days,"expected_range":[round(lo,2),round(hi,2)],"anomalies":[{"value":v,"index":i} for i,v in enumerate(vals) if v<lo or v>hi],"n":len(vals)}

    @mcp.tool()
    def calculate_sleep_debt(days:int=14)->dict[str,Any]:
        """Estimate sleep debt against a configurable 8-hour target using Oura daily sleep duration."""
        from oura_service import _fetch_collection
        end=date.today(); start=end-timedelta(days=max(1,min(days,90))-1)
        rows=_fetch_collection("daily_sleep",start.isoformat(),end.isoformat(),max_records=1000).get("data",[])
        # Prefer contributors.total_sleep_duration when present; fall back to total_sleep_duration.
        vals=[]
        for r in rows:
            v=r.get("contributors",{}).get("total_sleep_duration",r.get("total_sleep_duration"))
            if isinstance(v,(int,float)): vals.append(float(v))
        target=8*3600; debt=sum(max(0,target-v) for v in vals); avg=mean(vals)/3600 if vals else None
        return {"days_with_data":len(vals),"target_hours":8,"average_sleep_hours":round(avg,2) if avg else None,"estimated_debt_hours":round(debt/3600,2)}

    @mcp.tool()
    def calculate_sleep_regularity(days:int=30)->dict[str,Any]:
        """Measure sleep/wake timing regularity from detailed Oura sleep records."""
        from oura_service import _fetch_collection
        end=date.today(); start=end-timedelta(days=max(7,min(days,90))-1)
        rows=_fetch_collection("sleep",start.isoformat(),end.isoformat(),max_records=2000).get("data",[])
        starts=[]; ends=[]
        from datetime import datetime
        for r in rows:
            for field,target in (("bedtime_start",starts),("bedtime_end",ends)):
                v=r.get(field)
                if v:
                    try: target.append(datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()%86400)
                    except Exception: pass
        def sd(a):
            if len(a)<2:return None
            m=mean(a); return sqrt(sum((x-m)**2 for x in a)/len(a))/3600
        return {"window_days":days,"records":len(rows),"bedtime_std_hours":round(sd(starts),2) if sd(starts)!=None else None,"wake_time_std_hours":round(sd(ends),2) if sd(ends)!=None else None,"interpretation":"lower variation means more regular timing"}

    @mcp.tool()
    def correlate_oura_metrics(metric_a:str="sleep_score",metric_b:str="readiness_score",days:int=90)->dict[str,Any]:
        """Calculate Pearson correlation between two daily Oura metrics over the same period."""
        from oura_service import _fetch_collection
        mapping={"sleep_score":("daily_sleep","score"),"readiness_score":("daily_readiness","score"),"activity_score":("daily_activity","score"),"stress_high":("daily_stress","stress_high"),"resting_heart_rate":("daily_readiness","contributors.resting_heart_rate"),"hrv_balance":("daily_readiness","contributors.hrv_balance"),"recovery_index":("daily_readiness","contributors.recovery_index"),"temperature_deviation":("daily_readiness","temperature_deviation")}
        if metric_a not in mapping or metric_b not in mapping: raise ValueError("Unsupported metric")
        end=date.today(); start=end-timedelta(days=max(7,min(days,365))-1)
        ra=_fetch_collection(mapping[metric_a][0],start.isoformat(),end.isoformat(),max_records=3000).get("data",[])
        rb=_fetch_collection(mapping[metric_b][0],start.isoformat(),end.isoformat(),max_records=3000).get("data",[])
        def keyed(rows,key):
            out={}
            for r in rows:
                d=r.get("day") or str(r.get("timestamp",""))[:10]
                v=r
                for k in key.split('.'): v=v.get(k) if isinstance(v,dict) else None
                if d and isinstance(v,(int,float)): out[d]=float(v)
            return out
        a=keyed(ra,mapping[metric_a][1]); b=keyed(rb,mapping[metric_b][1]); dayset=sorted(set(a)&set(b)); av=[a[d] for d in dayset]; bv=[b[d] for d in dayset]
        r=_pearson(av,bv)
        return {"metric_a":metric_a,"metric_b":metric_b,"days":len(dayset),"pearson_r":round(r,4),"strength":"strong" if abs(r)>=.7 else "moderate" if abs(r)>=.4 else "weak" if abs(r)>=.2 else "minimal","direction":"positive" if r>0 else "negative" if r<0 else "none","warning":"Correlation does not establish causation."}
