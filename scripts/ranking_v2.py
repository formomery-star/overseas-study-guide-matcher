"""Transparent preference ordering; no synthetic school rules or fit scores.

Only reviewed programme tags may discriminate schools within the same direction.
Absent tags leave ties. Parents' occupations never supply preference or money.
"""
import re
from match_v2 import REGIONS, program_value

def reviewed_features(program,evidence,today):
    features=program_value(program,'matching_features',evidence,today)
    if not isinstance(features,dict):return {},[]
    if 'items' not in features:return features,[]
    interests=set();activities=set();accepted=[]
    # Each label must carry its own reviewed course evidence; a verified wrapper
    # cannot launder demo tags or a pending item into the ranking.
    for item in features.get('items',[]):
        if not isinstance(item,dict) or item.get('review')!='verified' or item.get('basis')!='official_curriculum':continue
        if not item.get('tag_id') or not item.get('zh_label') or not item.get('source_locator') or not item.get('basis_summary'):continue
        proxy={'facts':{'tag':{'value':item,'status':'verified','evidence_ids':item.get('evidence_ids'),
                              'scope':item['basis_summary']}}}
        if program_value(proxy,'tag',evidence,today) is None:continue
        interests.update(t for t in item.get('interest_tags',[]) if isinstance(t,str))
        activities.update(t for t in item.get('activity_tags',[]) if isinstance(t,str))
        accepted.append(item)
    return {'interest_tags':sorted(interests),'activity_tags':sorted(activities)},accepted

def rank_candidates(rows,programs,profile,evidence,today,priority_regions=None):
    by={p['id']:p for p in programs};priority=[REGIONS.get(x,x) for x in (priority_regions or [])]
    interests=profile.get('interests',{})
    wanted=set(interests.get('favorite_subjects',[])+interests.get('explicit_directions',[])+interests.get('liked_tasks',[]))
    rejected=set(interests.get('disliked_subjects',[])+interests.get('disliked_tasks',[]))
    wanted-=rejected
    activity=profile.get('materials',{}).get('activities',{}).get('records',[])
    activity_tags={t for r in activity for t in r.get('tags',[]) if isinstance(t,str)}
    ranked=[]
    for r in rows:
        if r['bucket'] not in ('pending','condition_passed'):continue
        features,items=reviewed_features(by.get(r['program_id'],{}),evidence,today)
        tags=features.get('interest_tags',[]);tasks=features.get('activity_tags',[])
        hits=sorted(wanted&set(tags));ahits=sorted(activity_tags&set(tasks))
        idx=priority.index(r['country_code']) if r['country_code'] in priority else len(priority)
        key=(0 if r['bucket']=='condition_passed' else 1,idx,-len(hits),-len(ahits))
        ranked.append({**r,'rank_key':list(key),'reason_breakdown':{
            'condition_tier':r['bucket'],'region_priority':idx if priority else None,
            'interest_hits':hits,'activity_hits':ahits,'reviewed_program_features':bool(tags or tasks),
            'feature_evidence':[{'tag_id':i['tag_id'],'label':i['zh_label'],'evidence_ids':i['evidence_ids'],
                                 'source_locator':i['source_locator'],'basis_summary':i['basis_summary']}
                                for i in items if set(i.get('interest_tags',[]))&set(hits) or set(i.get('activity_tags',[]))&set(ahits)],
            'preference_note':'课程关联用于探索排序，不代表录取加分；未命中也不证明学校没有该特色',
            'resource_note':'家庭支持只作准备资源说明；不由家长职业推断预算、人脉或录取优势'}})
    ranked.sort(key=lambda r:r['rank_key'])
    return ranked
