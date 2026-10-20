"""Scoped Food/Biology pilot rules, using reviewed actual transcripts.

Grade vectors are not grade sums. Subject aliases and practical exemptions need
an independent, programme-bound review; missing routes never mean rejection.
"""
import datetime as dt
import hashlib,json,re
from qualification_sets import ib_diploma,date,answer,unknown
GRADES={'A*':6,'A':5,'B':4,'C':3,'D':2,'E':1,'U':0}
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()
def combine(checks):
 states=[c['state'] for c in checks]
 return answer('not_satisfied' if 'not_satisfied' in states else 'unknown' if 'unknown' in states else 'satisfied','成绩与先修子项分别核对；其余录取条件另审',checks=checks)

def transcript(rule,value,today):
 route=rule.get('route')
 if route=='IB_DIPLOMA_FINAL_3HL':
  status=ib_diploma({'total_minimum':0,'hl_minimum':0,'hl_count':3},value,today)
  return status,([x for x in value['subjects'] if x['level']=='HL'] if status['state']=='satisfied' else [])
 if route!='UK_GCE_A_LEVEL_FINAL_3':return unknown('未实现的资格路径'),[]
 if (not isinstance(value,dict) or value.get('qualification')!='UK_GCE_A_LEVEL' or value.get('complete') is not True
     or value.get('record_type')!='achieved' or value.get('result_basis')!='single_session'):
  return unknown('仅覆盖已核实得、单场、完整三门英国GCE A-level'),[]
 issued=date(value.get('issued_on'));session=value.get('session');rows=value.get('subjects')
 if (not isinstance(today,dt.date) or issued is None or issued>today or not isinstance(session,str)
     or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',session) or date(session+'-01') is None or date(session+'-01')>issued
     or not isinstance(rows,list) or len(rows)!=3):return unknown('考试场次、出分日期或三门范围待核'),[]
 seen=set()
 for row in rows:
  if (not isinstance(row,dict) or not isinstance(row.get('subject'),str) or not row['subject'].strip()
      or row['subject'].strip().casefold() in seen or not isinstance(row.get('grade'),str) or row.get('grade') not in GRADES or row.get('session')!=session):
   return unknown('科目、等级或场次不一致'),[]
  seen.add(row['subject'].strip().casefold())
 return answer('satisfied','三门实得成绩结构有效'),rows

def credential(rule,value,today):
 structural,rows=transcript(rule,value,today)
 if structural['state']!='satisfied':return structural
 is_ib=rule['route']=='IB_DIPLOMA_FINAL_3HL';minimum=rule.get('grade_vector')
 if (not isinstance(minimum,list) or len(minimum)!=3
     or (is_ib and any(type(x) is not int or not 1<=x<=7 for x in minimum))
     or (not is_ib and any(not isinstance(x,str) or x not in GRADES for x in minimum))):return unknown('逐科成绩门槛未核')
 got=sorted([r['score'] if is_ib else GRADES[r['grade']] for r in rows],reverse=True)
 need=sorted(minimum if is_ib else [GRADES[x] for x in minimum],reverse=True)
 checks=[answer('satisfied' if all(a>=b for a,b in zip(got,need)) else 'not_satisfied','逐项比较三门成绩，不用合计分替代',actual=got,minimum=need)]
 excluded={x.casefold() for x in rule.get('excluded_subjects',[])}
 if any(x['subject'].strip().casefold() in excluded for x in rows):checks.append(answer('not_satisfied','完整三门组合含官方排除科目'))
 if is_ib:
  floor=rule.get('total_minimum')
  if floor is None:checks.append(unknown('官网未明确IB总分要求；仅HL分档可判，不自行补总分'))
  elif type(floor) is not int or not 0<=floor<=45:return unknown('IB总分门槛格式无效')
  else:checks.append(answer('satisfied' if value['total']>=floor else 'not_satisfied','IB总分核对',actual=value['total'],minimum=floor))
 return combine(checks)

def al_subject_minimum(rule,value,today):
    """A-level 特定科目最低分检查（如 LSE 经济学要求数学 A*）。

    仅检查已核实得、单场、完整三门 UK GCE A-level 成绩单中指定科目达到最低等级；
    不替代总门槛比较，不猜测科目等同。
    """
    subject=rule.get('subject');minimum=rule.get('minimum')
    if (not isinstance(subject,str) or not subject.strip()
            or not isinstance(minimum,str) or minimum not in GRADES):
        return unknown('科目名称或最低等级待核')
    structural,rows=transcript(rule,value,today)
    if structural['state']!='satisfied':return structural
    target=subject.strip().casefold()
    matched=[r for r in rows if r['subject'].strip().casefold()==target]
    if not matched:
        # Exact-name matching cannot prove that an unfamiliar label is a different
        # subject. A programme may opt into conservative handling of this gap.
        if rule.get('missing_subject_state')=='unknown':
            return unknown('指定科目名称未精确对应；需审阅原始成绩单，不能猜测等同或排除')
        return answer('not_satisfied','成绩单中未找到指定科目',subject=subject)
    got=GRADES[matched[0]['grade']];need=GRADES[minimum]
    return answer('satisfied' if got>=need else 'not_satisfied','指定科目最低等级核对',
                  subject=matched[0]['subject'],actual=matched[0]['grade'],minimum=minimum)


def al_subject_mix(rule,value,today):
 """Exact official subject sets only; unfamiliar names require review."""
 structural,rows=transcript(rule,value,today)
 if structural['state']!='satisfied':return structural
 groups=[]
 for key in ('preferred_subjects','non_preferred_subjects','excluded_subjects'):
  xs=rule.get(key)
  if not isinstance(xs,list) or any(not isinstance(x,str) or not x.strip() for x in xs):return unknown('科目分类规则格式待核')
  groups.append({x.strip().casefold() for x in xs})
 preferred,other,excluded=groups;minimum=rule.get('preferred_minimum')
 if type(minimum) is not int or not 0<=minimum<=3 or not preferred or preferred&other or preferred&excluded or other&excluded:return unknown('科目分类或最低数量规则待核')
 names={x['subject'].strip().casefold() for x in rows}
 if names&excluded:return answer('not_satisfied','三门中含标准录取组合不计入的科目，另需三门完整A-level',excluded=sorted(names&excluded))
 if names-(preferred|other):return unknown('科目名未落入本项目已核分类；不猜等同，也不据此排除')
 pairs=rule.get('review_pairs',[])
 if not isinstance(pairs,list) or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(x,str) for x in p) for p in pairs):return unknown('重叠科目规则待核')
 if any({x.casefold() for x in p}<=names for p in pairs):return unknown('科目内容重叠，需结合申请材料审阅；不机械按两门计')
 count=len(names&preferred)
 return answer('satisfied' if count>=minimum else 'not_satisfied','传统学术科目最低数量；选拔偏好不等于硬门槛',actual=count,minimum=minimum)

def secondary(value,today,minimum,english_minimum=4):
 if type(minimum) is not int or not 1<=minimum<=9 or type(english_minimum) is not int or not 1<=english_minimum<=9:return unknown('GCSE门槛配置待核')
 if (not isinstance(value,dict) or value.get('qualification')!='GCSE_9_1'
     or value.get('complete') is not True or value.get('record_type')!='achieved'):
  return unknown('GCSE数制或等同资格待核；不从IB/雅思自动推定满足')
 issued=date(value.get('issued_on'))
 if issued is None or issued>today:return unknown('GCSE出分日期待核')
 scores=[value.get('mathematics'),value.get('english_language')]
 if any(type(s) is not int or not 1<=s<=9 for s in scores):return unknown('GCSE数学/英语Language成绩待核')
 return answer('satisfied' if scores[0]>=minimum and scores[1]>=english_minimum else 'not_satisfied','GCSE数学与英语Language最低分',actual=scores,minimum=[minimum,english_minimum])

def subjects(rule,value,review,gcse,today):
 structural,rows=transcript(rule,value,today)
 if structural['state']!='satisfied':return structural
 checked=date(review.get('reviewed_on')) if isinstance(review,dict) else None
 if (not isinstance(review,dict) or review.get('review_complete') is not True
     or review.get('program_id')!=rule.get('program_id') or review.get('policy_year')!=2027
     or review.get('transcript_sha256')!=digest(value) or not review.get('reviewer')
     or checked is None or checked>today):return unknown('项目科目认定与成绩单未绑定或审阅缺失')
 mapped=review.get('subjects');names=[r['subject'] for r in rows]
 if not isinstance(mapped,dict) or set(mapped)!=set(names):return unknown('需要逐一审阅三门科目，不按相似名称猜等同')
 core=set(rule.get('core_subjects',[]));related=set(rule.get('related_subjects',[]));accepted=core|related|{'Other'}
 for item in mapped.values():
  if not isinstance(item,dict) or not isinstance(item.get('canonical'),str) or item.get('canonical') not in accepted or not item.get('basis') or not item.get('source_refs'):
   return unknown('科目分类及接受依据待核')
 science_names=[item['canonical'] for item in mapped.values() if item['canonical']!='Other']
 if len(science_names)!=len(set(science_names)):return unknown('同一科学科目重复映射，不能计为两门')
 cs=[r for r in rows if mapped[r['subject']]['canonical'] in core]
 rs=[r for r in rows if mapped[r['subject']]['canonical'] in related]
 checks=[];kind=rule.get('kind');is_ib=rule['route']=='IB_DIPLOMA_FINAL_3HL'
 if kind=='FOOD':checks.append(answer('satisfied' if len(cs)>=1 and len(cs)+len(rs)>=2 else 'not_satisfied','两门已认定科学科目，其中至少一门生物/化学/物理/数学'))
 elif kind=='BIO':
  bio=[r for r in rows if mapped[r['subject']]['canonical']=='Biology']
  if not bio:checks.append(answer('not_satisfied','缺少生物科目（IB需HL）'))
  elif len(cs)==1:
   mark=bio[0]['score'] if is_ib else GRADES[bio[0]['grade']];need=6 if is_ib else GRADES['A']
   state='satisfied' if mark>=need else 'unknown' if rs else 'not_satisfied'
   checks.append(answer(state,'仅生物为科学时需IB HL6/A-level A；只有另一门相关科目且生物低于该线时需校方确认，不能猜等同',actual=mark,minimum=need))
  else:checks.append(answer('satisfied','含生物与其他科学；第二科学仅优先，不普遍强制'))
 else:return unknown('未核的科学项目规则')
 if not is_ib:
  for row in cs+rs:
   item=mapped[row['subject']];required=item.get('practical_required')
   if type(required) is not bool or not item.get('practical_basis'):checks.append(unknown('实践考核适用性待核：'+row['subject']))
   elif required:
    v=row.get('practical_pass')
    checks.append(answer('unknown' if type(v) is not bool else 'satisfied' if v else 'not_satisfied','实践考核：'+row['subject']))
 minimum=rule.get('gcse_math_minimum')
 if type(minimum) is not int or not 1<=minimum<=9:return unknown('GCSE门槛配置无效')
 checks.append(secondary(gcse,today,minimum))
 return combine(checks)
