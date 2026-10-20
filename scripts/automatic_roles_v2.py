"""Data-driven roles: benchmarks separate from student-specific candidates."""
from candidate_selection_v2 import ASIA
from match_v2 import program_value, numeric
import datetime as dt


def tuition_reference(program,profile,evidence,today,scenario,fee_scope_confirmed=False):
    t=program_value(program,'tuition',evidence,today)
    if not isinstance(t,dict):return {'state':'unknown','reason':'学费资料待核'}
    result={'state':'unknown','reason':'仅显示原年学费；费用身份或完整预算待核','value':t}
    rate=(scenario or {}).get('fx_cny',{}).get(t.get('currency'))
    if not numeric(rate) or rate<=0:return result
    lo,hi=t.get('amount_min'),t.get('amount_max');cap=profile.get('family_context',{}).get('annual_budget_cny')
    if not numeric(lo) or not numeric(hi) or not 0<=lo<=hi:return result
    result['cny_range']=[lo*rate,hi*rate];result['fx']=rate
    # Budget exclusion needs explicitly accepted fee category and target-year tuition.
    year=profile.get('identity',{}).get('入学年月','')[:4]
    if fee_scope_confirmed and str(t.get('base_year'))==year and numeric(cap) and cap>=0:
        result['state']='not_satisfied' if lo*rate>cap else 'satisfied' if hi*rate<=cap else 'unknown'
        result['reason']='申报年预算对照已选择身份的原年学费；不含生活费杂费，不代表全包负担能力'
    return result


def select_roles(group,programs,screenings,evidence,today,benchmark_sets,priority_regions=None,profile=None):
    from match_v2 import REGIONS
    by={p['id']:p for p in programs};rows=group['programs'];mid=group['major_id']
    screen={s['program_id']:s for s in screenings}
    priority=[REGIONS.get(x,x) for x in (priority_regions or [])]
    result={}
    for role,rank_key in (('global','world_rank'),('asia','asia_rank')):
        candidates=[]
        for b in benchmark_sets:
            if mid not in b.get('major_ids',[]):continue
            for rec in b.get('records',[]):
                rank=rec.get(rank_key,{})
                if rank.get('value')!=1 or rank.get('status') not in ('verified','official_university_claim','university_derived_claim'):continue
                refs=rank.get('evidence_ids',[])
                if not refs or any(ref not in evidence for ref in refs):continue
                try:
                    if any(not evidence[ref].get('reviewed_by') or not 0<=(today-dt.date.fromisoformat(evidence[ref]['checked_on'])).days<=90 for ref in refs):continue
                except (ValueError,KeyError,TypeError):continue
                paths=[r for r in rows if r['school_id']==rec['school_id'] and not r['identity_gaps'] and r['bucket'] != 'historical_reference']
                if role=='asia':paths=[r for r in paths if r['country_code'] in ASIA]
                for r in paths:
                    candidates.append({'program_id':r['program_id'],'school_id':r['school_id'],
                        'label':rec.get('display_label','学科标杆参考'),'basis':'subject_benchmark_reference_not_personal_fit',
                        'rank_evidence':rank,'ranking_year':b.get('ranking_edition'),'subject':b.get('subject'),
                        'condition_state':r['condition_state'], 'personal_candidate':r['bucket'] in ('pending','condition_passed'),
                        'reference_gaps':rec.get('gaps',[])})
        candidates={c['program_id']:c for c in candidates}
        result[role]={'selected':next(iter(candidates.values())) if len(candidates)==1 else None,
                      'alternatives':list(candidates.values()),'reason':'依据已收录学科排名，仅作实力参照；该校可能不符合本人地区、成绩或预算条件' if len(candidates)==1 else '无唯一可追溯学科第一标杆；留空待核'}
    for role in ('fit','asia_fit'):
        candidates=[r for r in rows if r['bucket'] in ('pending','condition_passed') and (role!='asia_fit' or r['asia'] is True)]
        from ranking_v2 import rank_candidates
        ranked=rank_candidates(candidates,programs,profile or {},evidence,today,priority_regions)
        candidates=[r for r in ranked if r['rank_key']==ranked[0]['rank_key']] if ranked else []
        selected=None
        if len(candidates)==1:
            r=candidates[0];selected={'program_id':r['program_id'],'school_id':r['school_id'],'label':r['label'],
                'basis':'conditions_then_explicit_region_priority_then_reviewed_preferences','condition_state':r['condition_state'],
                'reason_breakdown':r['reason_breakdown'],
                'personal_fit_confirmed':False,'unknown_conditions':r['unknown_conditions']}
        result[role]={'selected':selected,'alternatives':candidates,'ranked_candidates':ranked,
                     'reason':'按条件、明确地区顺序及已核项目标签排序；唯一候选仍保留待核' if selected else '并列或无可用候选，不以编号、名气、资料条数强选一校'}
    return result
