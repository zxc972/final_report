"""Host-generated failures are distinct from Agent argument and science errors."""
from __future__ import annotations
from collections import Counter

# Default remains compatible; a closed evaluation can stop on the first defect.
STOP_AFTER = 2

class SystemDefect(RuntimeError):
    def __init__(self,code,message,**details):
        super().__init__(message);self.code=code;self.details=details

class SystemDefectStop(RuntimeError):
    pass

def latest(tools):
    saved=tools.control_store.latest('system_defects') if tools.control_store else None
    return saved['record'] if saved else {'events':[],'counts':{},'stop':False}

def _record_unlocked(tools,error):
    data=latest(tools);events=list(data['events']);session=tools.session
    charged=False
    if session is not None:
        reservation=session.record.get('last_planning_reservation')
        exempt=session.record.setdefault('system_defect_exempt_model_calls',[])
        if (session.state()['phase'] in {'unplanned','planned'} and reservation == tools.model_calls and reservation not in exempt):
            exempt.append(reservation)
            session.record['planning_model_calls']=max(0,session.record.get('planning_model_calls',0)-1)
            charged=True
            from .analysis_planning_budget import snapshot
            tools.control_store.save('phase_budget',snapshot(session))
    events.append({'code':error.code,'message':str(error),'details':error.details,
                   'actual_model_calls':tools.model_calls,'planning_call_exempted':charged})
    counts=dict(Counter(e['code'] for e in events));stop=any(n>=STOP_AFTER for n in counts.values())
    data={'events':events,'counts':counts,'stop':stop}
    if tools.control_store:tools.control_store.save('system_defects',data)
    if session is not None:
        session.record['system_defect_stop']=stop
        session.record['next']='Stop and report the host defect' if stop else 'Report host defect; preserve the requested scope'
        tools.control_store.save('session',session.record)
    if tools.events:tools.events.append('plan','failed','Host system defect',events[-1])
    return {'status':'system_defect','error_code':error.code,'error':str(error),'details':error.details,
            'same_defect_count':counts[error.code],'stop_required':stop,'reflection_required':False,
            'planning_quota_charged':False,'actual_model_calls_retained':tools.model_calls,
            'next':'Stop and report the host defect' if stop else 'Report the host defect; do not reduce the user task or invent a workaround'}

def check_stop(tools):
    if latest(tools).get('stop'):raise SystemDefectStop(f'Host system defect threshold {STOP_AFTER} reached; stop this analysis without another model call')


def record(tools,error):
    with tools._lock:
        return _record_unlocked(tools,error)
