"""Reviewed exam collections. No fuzzy subject aliases or predicted-score promotion."""
import datetime as dt
import itertools
import math
import re
import hashlib
import json

def answer(state,reason,**kw):return dict(state=state,reason=reason,**kw)
def unknown(reason):return answer('unknown',reason)
def number(x):return type(x) in (int,float) and math.isfinite(x)
def date(x):
    if not isinstance(x,str):return None
    try:return dt.date.fromisoformat(x)
    except ValueError:return None

def ib_diploma(rule,value,today):
    """Scoped check of an awarded, single-session, three-HL diploma transcript.

    This validates score transcription, not the IB's award decision. Four HLs,
    predicted results and mixed sessions need their own reviewed policy.
    """
    total_min=rule.get('total_minimum');hl_min=rule.get('hl_minimum')
    if (type(total_min) is not int or not 0<=total_min<=45
        or type(hl_min) is not int or not 0<=hl_min<=21
        or rule.get('hl_count')!=3 or type(rule.get('hl_count')) is not int):
        return unknown('IB门槛或三门HL范围未核')
    if not isinstance(today,dt.date) or not isinstance(value,dict):return unknown('IB记录或核验日期缺失')
    if (value.get('qualification')!='IB_DIPLOMA' or value.get('complete') is not True
        or value.get('record_type')!='achieved' or value.get('diploma_awarded') is not True
        or value.get('result_basis')!='single_session'):
        return unknown('仅检查已颁发完整文凭的单场实际成绩；其他路线待核')
    issued=date(value.get('issued_on'));session=value.get('session')
    if (issued is None or issued>today or not isinstance(session,str)
        or not re.fullmatch(r'\d{4}-(05|11)',session)
        or date(session+'-01') is None or date(session+'-01')>issued):
        return unknown('IB考试场次及出分日期待核')
    rows=value.get('subjects');core=value.get('core_points');total=value.get('total')
    if (not isinstance(rows,list) or len(rows)!=6 or type(core) is not int or not 0<=core<=3
        or type(total) is not int or not 0<=total<=45):return unknown('IB六科、核心加分或总分格式无效')
    subjects=set();scores=[];hl=[]
    for row in rows:
        if (not isinstance(row,dict) or not isinstance(row.get('subject'),str) or not row['subject'].strip()
            or row['subject'].strip().casefold() in subjects or row.get('level') not in ('HL','SL')
            or type(row.get('score')) is not int or not 1<=row['score']<=7
            or row.get('session')!=session):return unknown('IB科目重复、分数/层级或场次不一致')
        subjects.add(row['subject'].strip().casefold());scores.append(row['score'])
        if row['level']=='HL':hl.append(row['score'])
    if len(hl)!=3:return unknown('本规则仅覆盖三门HL；不自行选择四门HL中的三门')
    if sum(scores)+core!=total:return unknown('IB总分与六科加核心分不一致')
    state='satisfied' if total>=total_min and sum(hl)>=hl_min else 'not_satisfied'
    return answer(state,'仅文凭总分与三门HL合计核对；先修、语言及材料另审',
                  total=total,hl_total=sum(hl),session=session,
                  check_scope='awarded_single_session_three_HL_total_thresholds_only')

def ib_subject_minimum(rule,value,selection,today):
    """Match a reviewed subject selection against its exact full transcript.

    Selection is programme-specific independent review, not fuzzy string matching.
    This checks marks only; it cannot certify university acceptance of a subject.
    """
    thresholds=rule.get('minimum_by_level')
    if (not isinstance(thresholds,dict) or set(thresholds)!={'HL','SL'}
        or any(type(x) is not int or not 1<=x<=7 for x in thresholds.values())
        or not isinstance(rule.get('program_id'),str) or not rule['program_id']
        or not isinstance(rule.get('requirement_key'),str) or not rule['requirement_key']):
        return unknown('IB科目分层门槛或项目范围未核')
    allowed_levels=rule.get('allowed_levels',['HL','SL'])
    if (not isinstance(allowed_levels,list) or not allowed_levels
        or any(x not in ('HL','SL') for x in allowed_levels)
        or len(allowed_levels)!=len(set(allowed_levels))):
        return unknown('IB先修课程允许层级未核')
    structural=ib_diploma(dict(total_minimum=0,hl_minimum=0,hl_count=3),value,today)
    if structural['state']!='satisfied':return structural
    try:
        digest=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    except (TypeError,ValueError):return unknown('成绩单无法生成稳定标识')
    if (not isinstance(selection,dict) or selection.get('review_complete') is not True
        or selection.get('transcript_sha256')!=digest
        or selection.get('program_id')!=rule['program_id']
        or selection.get('requirement_key')!=rule['requirement_key']):
        return unknown('科目认定未完成、与本成绩单不一致或项目范围不符')
    names=selection.get('accepted_subjects')
    if not isinstance(names,list) or any(not isinstance(n,str) or not n.strip() for n in names):
        return unknown('已审科目列表格式待核')
    names=[n.strip().casefold() for n in names]
    if len(names)!=len(set(names)):return unknown('已审科目重复')
    rows={r['subject'].strip().casefold():r for r in value['subjects']}
    if any(n not in rows for n in names):return unknown('已审科目不在本次完整成绩单中')
    checks=[dict(subject=rows[n]['subject'],level=rows[n]['level'],score=rows[n]['score'],
                 minimum=thresholds[rows[n]['level']]) for n in names]
    ok=any(x['level'] in allowed_levels and x['score']>=x['minimum'] for x in checks)
    return answer('satisfied' if ok else 'not_satisfied','在独立审阅确认的适用科目中核对HL/SL最低分；其他录取要求另审',
                  checks=checks,check_scope='reviewed_subject_marks_only',transcript_sha256=digest)


def evaluate(rule,value,today,cutoff=None):
    if not isinstance(value,dict) or value.get('complete') is not True:
        return unknown('考试材料未确认完整，不能把漏填当没有')
    rows=value.get('attempts')
    if not isinstance(rows,list) or len(rows)>100:return unknown('考试记录格式或数量需人工复核')
    if not isinstance(today,dt.date):return unknown('缺少核验日期')
    for x in rows:
        if not isinstance(x,dict) or x.get('record_type')!='achieved':return unknown('只接受已取得并核验的考试成绩')
        d=date(x.get('date'))
        if d is None or d>today:return unknown('考试日期缺失或位于未来')
    if rule['op']=='ap_set':return ap_set(rule,rows)
    return exam_attempts(rule,rows,cutoff)

def ap_set(rule,rows):
    allowed=rule.get('allowed_subjects');minimum=rule.get('minimum_score');count=rule.get('minimum_count')
    sessions_max=rule.get('maximum_sittings');required=rule.get('required_subjects',{})
    if (not isinstance(allowed,list) or not allowed or any(not isinstance(s,str) or not s for s in allowed)
        or len(allowed)!=len(set(allowed)) or type(minimum) is not int or not 1<=minimum<=5
        or type(count) is not int or not 1<=count<=50 or type(sessions_max) is not int or not 1<=sessions_max<=3
        or not isinstance(required,dict) or any(s not in allowed or type(v) is not int or not 1<=v<=5 for s,v in required.items())):
        return unknown('AP规则的科目、数量、分数或考试次数范围无效')
    for x in rows:
        if (x.get('name')!='AP' or x.get('scale')!=5 or not isinstance(x.get('subject'),str)
            or not x['subject'] or type(x.get('score')) is not int or not 1<=x['score']<=5
            or not isinstance(x.get('session'),str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',x['session'])
            or x['session']!=x['date'][:7]):return unknown('AP科目、分制或考试场次日期需复核')
    sessions=sorted({x['session'] for x in rows})
    if len(sessions)>12:return unknown('考试场次过多，转人工复核')
    best=0
    # Select at most the permitted sittings; retakes never create extra subjects.
    for size in range(1,min(sessions_max,len(sessions))+1):
        for selected in itertools.combinations(sessions,size):
            scores={}
            for x in rows:
                if x['session'] in selected and x['subject'] in allowed:
                    scores[x['subject']]=max(scores.get(x['subject'],0),x['score'])
            qualifying=sorted(s for s,v in scores.items() if v>=minimum)
            best=max(best,len(qualifying))
            if len(qualifying)>=count and all(scores.get(s,0)>=v for s,v in required.items()):
                return answer('satisfied','所选AP科目组合达到已核最低考试要求',subjects=qualifying,sessions=list(selected))
    return answer('not_satisfied','完整已核成绩中未找到符合科目及场次限制的AP组合',best_subject_count=best)

def exam_attempts(rule,rows,cutoff):
    cutoff=date(cutoff);years=rule.get('max_age_years');scale=rule.get('scale');minimum=rule.get('minimum')
    sections=rule.get('sections');name=rule.get('name');version=rule.get('version')
    metadata=rule.get('required_metadata',{})
    if (not isinstance(metadata,dict) or any(not isinstance(k,str) or not k or type(v) not in (str,bool,int)
                                            for k,v in metadata.items())):
        return unknown('考试形式与成绩来源条件格式无效')
    if (cutoff is None or type(years) is not int or not 1<=years<=10 or cutoff.year<=years
        or not number(scale) or scale<=0 or not number(minimum) or not 0<=minimum<=scale
        or not isinstance(name,str) or not isinstance(version,str) or not name or not version
        or not isinstance(sections,dict) or (not sections and rule.get('overall_only') is not True)):return unknown('标准化考试版本、分制、有效期或截止日未核')
    years_allowed=rule.get('valid_on_years')
    if years_allowed is None:
        years_allowed=[rule.get('valid_on_year')]
    elif 'valid_on_year' in rule:
        return unknown('申请日期年份规则冲突')
    if (not isinstance(years_allowed,list) or not years_allowed
        or any(type(y) is not int or not 1900<=y<=2100 for y in years_allowed)
        or len(set(years_allowed))!=len(years_allowed) or cutoff.year not in years_allowed):
        return unknown('截止日不在已核申请日期范围')
    for spec in sections.values():
        if not isinstance(spec,dict) or not number(spec.get('min')) or not number(spec.get('max')) or not 0<=spec['min']<=spec['max']:
            return unknown('考试分项规则无效')
    try:floor=cutoff.replace(year=cutoff.year-years)
    except ValueError:floor=cutoff.replace(year=cutoff.year-years,day=28)
    uncertain=False
    for x in rows:
        if any(k not in x or type(x[k]) is not type(v) or x[k]!=v for k,v in metadata.items()):
            uncertain=True;continue
        if x.get('name')!=name or x.get('version')!=version or x.get('scale')!=scale:
            uncertain=True;continue
        if not number(x.get('overall')) or not 0<=x['overall']<=scale or not isinstance(x.get('sections'),dict):
            uncertain=True;continue
        values=x['sections']
        if any(not number(values.get(k)) or not 0<=values[k]<=s['max'] for k,s in sections.items()):
            uncertain=True;continue
        if rule.get('sum_sections') is True and sum(values[k] for k in sections)!=x['overall']:
            uncertain=True;continue
        if floor<=date(x['date'])<=cutoff and x['overall']>=minimum and all(values[k]>=s['min'] for k,s in sections.items()):
            return answer('satisfied','同一场考试达到各项门槛及日历年有效期',exam_date=x['date'])
    return unknown('存在未确认版本或小分的考试，需复核') if uncertain else answer('not_satisfied','完整成绩中没有单次考试同时满足各项门槛及有效期')
