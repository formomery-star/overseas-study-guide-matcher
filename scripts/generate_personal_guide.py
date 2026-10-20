"""Single form-to-guide entry point for all registered directions.

Provisional self-report screening is distinct from independently verified facts.
No direction-specific pilot_roles file is used.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import time
import copy
from intake_v2 import read_form, normalize
from match_v2 import propose_routes, screen_program, program_value, submitted_input_mode, combine
from form_rule_bridge import map_program
from candidate_selection_v2 import select_candidates
from automatic_roles_v2 import select_roles, tuition_reference
from generate import ROOT, Report, card, wheel, school_pages, BY, E

LABEL={'satisfied':'按填报值通过','not_satisfied':'按填报值不满足','unknown':'待核'}
GATE_NAMES={'catalog':'项目资料完整性','policy_year':'申请年份','high_school_entry':'高中毕业直入资格',
    'international_eligible':'国际生申请资格','degree_level':'本科学位路径','credential_requirements':'课程体系与总成绩',
    'subject_requirements':'专业先修科目','english_requirements':'语言成绩','additional_requirements':'附加申请材料',
    'student_region':'学生地区意向','parent_region':'家长许可地区','duration':'学制限制','budget':'全程费用覆盖',
    'tuition_reference':'学费与年预算','standardised_tests':'标准化考试','age_process':'年龄及签证材料'}

def friendly_reason(key,reason):
    text=reason
    for old,new in GATE_NAMES.items():text=text.replace(old,new)
    return text

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def chunks(seq,n):return [seq[i:i+n] for i in range(0,len(seq),n)]
def links(ids,evidence):
    return ' · '.join(f'<a href="{E(evidence[i].get("url"))}">{E(i)}</a>' for i in dict.fromkeys(ids) if i in evidence and evidence[i].get('url'))


def job_status_label(job, today):
    """Render vacancy status with its observation and expiry boundary."""
    today = dt.date.fromisoformat(today) if isinstance(today, str) else today
    status = job.get('vacancy_status')
    if status == 'closed':
        return '已截止历史样本'
    if status != 'open':
        return '当前在招状态待核'
    observed = job.get('observed_on') or '核验日期待核'
    closing_raw = job.get('application_closes_on')
    if closing_raw:
        closing = dt.date.fromisoformat(closing_raw)
        if closing < today:
            return f'招聘截止日期已过（{closing.isoformat()}）；状态需重查（原核验日 {observed}）'
        return f'官方页面显示开放至 {closing.isoformat()}（核验于 {observed}）'
    return f'官方页面曾显示开放（核验于 {observed}）；截止日待核，使用前需重查'


def cost_reference_rows(program,evidence,today):
    """Verified one-off charges remain separate from annual/full costs."""
    rows=[];refs=[]
    for key,label in [('application_fee_reference','一次申请费'),('fee_deposit_reference','入学保证金')]:
        value=program_value(program,key,evidence,today)
        if not isinstance(value,dict) or type(value.get('amount')) not in (int,float):continue
        note='一次申请；不按学年重复。' if key=='application_fee_reference' else '现金流单列；退还或抵毕业费用按校规，不重复计入毕业费。'
        rows.append('<div class="row"><b>'+E(label)+'</b><strong>'+E(f"{value['amount']:,.0f} {value.get('currency','')}")+'</strong><p>'+E(note)+'</p></div>')
        refs.extend(program['facts'][key].get('evidence_ids',[]))
    return ''.join(rows),refs

def living_observations(program):
    """Conflicting observations are visible evidence, never a computed budget."""
    fact=program.get('facts',{}).get('living_cost',{});value=fact.get('value')
    if fact.get('status')!='extracted' or not isinstance(value,dict):return ''
    parts=[]
    for row in value.get('conflicting_observations',[]):
        amounts=[]
        for key,label in [('accommodation','住宿'),('living','生活'),('living_and_other','生活及其他')]:
            if type(row.get(key)) in (int,float):amounts.append(label+f" {row[key]:,.0f} {value.get('currency','')}")
        if amounts:parts.append('、'.join(amounts))
    if not parts:return ''
    return '<div class="callout">待核口径：'+E('；另页为'.join(parts))+'。各页项目范围或月份未统一；不相加、不取平均，不作全年总额。</div>'

def cost_planning_page(program,evidence,today):
    """A labelled partial scenario is useful without bypassing the budget gate."""
    value=program_value(program,'cost_planning_reference',evidence,today)
    if not isinstance(value,dict) or value.get('illustration_only') is not True or value.get('not_for_budget_gate') is not True:
        return None
    rows=value.get('items',[])
    if not isinstance(rows,list) or len(rows)!=3 or any(not isinstance(x,dict) or type(x.get('amount')) not in (int,float) or not math.isfinite(x['amount']) or x['amount']<0 for x in rows):
        return None
    currency=value.get('currency','');total=sum(x['amount'] for x in rows)
    body='<div class="grid two">'
    for row in rows:
        body+=card(row['label'],f"{row['amount']:,.0f} {currency}",row.get('year_label','年份待核')+' · '+row.get('period_label','周期待核'))
    body+=card('规划小计 · 非完整总费用',f'{total:,.0f} {currency}','不同报价年组成的参考情景；不代表2027锁价')+'</div>'
    for note in value.get('assumptions',[]):body+='<div class="callout">'+E(note)+'</div>'
    tuition=program_value(program,'tuition',evidence,today)
    years=program_value(program,'duration_years',evidence,today)
    if isinstance(tuition,dict) and tuition.get('fee_mode')=='annual_review' and tuition.get('cohort_year')==program.get('policy_year'):
        cap=tuition.get('annual_increase_cap');base=tuition.get('amount_min')
        if (type(cap) in (int,float) and math.isfinite(cap) and 0<=cap<=1 and type(base) in (int,float)
                and math.isfinite(base) and base>=0 and type(years) is int and 0<years<=10
                and tuition.get('amount_max')==base and tuition.get('currency')==currency):
            capped=sum(base*(1+cap)**n for n in range(years))
            body+='<div class="row"><b>'+E(f'{years}年学费情景（仅学费）')+'</b><p>'+E(f'假设不涨价：{base*years:,.0f} {currency}；每年按{cap:.0%}上限推算：{capped:,.0f} {currency}。上限不等于实际涨幅。')+'</p></div>'
    refs=program['facts']['cost_planning_reference'].get('evidence_ids',[])+program.get('facts',{}).get('tuition',{}).get('evidence_ids',[])
    return body,refs

def cost_detail_page(program,evidence,today):
    """Show reviewed fee observations without converting conflicts into totals."""
    value=program_value(program,'cost_detail_reference',evidence,today)
    if not isinstance(value,dict) or value.get('not_for_budget_gate') is not True:return None
    rows=value.get('cards',[])
    if not isinstance(rows,list) or not 1<=len(rows)<=4:return None
    if any(not isinstance(row,dict) or any(not isinstance(row.get(k),str) for k in ('label','display','note')) for row in rows):return None
    body='<div class="grid two">'+''.join(card(row['label'],row['display'],row['note']) for row in rows)+'</div>'
    for note in value.get('caveats',[])[:3]:body+='<div class="callout">'+E(note)+'</div>'
    return body,program['facts']['cost_detail_reference'].get('evidence_ids',[])


def admission_detail_page(program,evidence,today,key='admission_detail_reference'):
    """Display reviewed pathway guidance; never turn reference years into gates."""
    value=program_value(program,key,evidence,today)
    if not isinstance(value,dict) or value.get('not_for_admission_gate') is not True:return None
    rows=value.get('cards',[])
    if not isinstance(rows,list) or not 1<=len(rows)<=4:return None
    if any(not isinstance(row,dict) or any(not isinstance(row.get(k),str) for k in ('label','display','note')) for row in rows):return None
    body='<div class="grid two">'+''.join(card(row['label'],row['display'],row['note']) for row in rows)+'</div>'
    body+='<div class="callout">'+E(value.get('boundary','参考流程不替代当年申请条件与学生材料核验。'))+'</div>'
    return body,program['facts'][key].get('evidence_ids',[])


def comparison_scope(config, programs, major_ids):
    """Reference coverage never supplies or overrides an automatic role."""
    if config is None:return []
    if not isinstance(config,dict) or config.get('reference_only') is not True:
        raise ValueError('资料对照必须明确 reference_only=true')
    ids=config.get('program_ids')
    if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids):
        raise ValueError('资料对照需要非空项目ID列表')
    by={p['id']:p for p in programs}
    if any(pid not in by or not set(by[pid]['major_ids'])&major_ids for pid in ids):
        raise ValueError('资料对照项目不存在或不属于学生意向方向')
    return list(dict.fromkeys(ids))


def career_detail_page(program,evidence,today):
    value=program_value(program,'career_detail_reference',evidence,today)
    if not isinstance(value,dict) or value.get('not_for_admission_gate') is not True:return None
    rows=value.get('cards',[])
    if not isinstance(rows,list) or not 1<=len(rows)<=4:return None
    if any(not isinstance(row,dict) or any(not isinstance(row.get(k),str) for k in ('label','display','note')) for row in rows):return None
    body='<div class="grid two">'+''.join(card(row['label'],row['display'],row['note']) for row in rows)+'</div>'
    boundary=value.get('boundary','专业实例不是个人就业承诺。')
    if boundary:body+='<div class="callout">'+E(boundary)+'</div>'
    return body,program['facts']['career_detail_reference'].get('evidence_ids',[])


def historical_employment_cards(program_ids,by,major_id,evidence):
    """Render explicitly scoped degree-level outcomes inside the existing employment section."""
    cards=[];refs=[]
    for pid in program_ids:
        program=by.get(pid,{})
        if major_id not in program.get('major_ids',[]):continue
        fact=program.get('facts',{}).get('career_outcomes',{})
        if not isinstance(fact,dict) or fact.get('status')!='verified':continue
        values=fact.get('value',{})
        if not isinstance(values,dict):continue
        for key,item in values.items():
            if not isinstance(item,dict) or not item.get('source_id'):continue
            eid=item['source_id']
            if eid not in evidence or eid not in fact.get('evidence_ids',[]):continue
            label=item.get('degree_label') or program.get('official_name',{}).get('value') or pid
            cohort=item.get('cohort','历史届别')
            employed=item.get('employed_among_labour_force_pct')
            ft=item.get('full_time_permanent_among_labour_force_pct')
            median=item.get('gross_salary_median')
            p25=item.get('gross_salary_p25');p75=item.get('gross_salary_p75')
            currency=item.get('salary_currency','')
            summary='劳动力人口就业率 '+(str(employed)+'%' if isinstance(employed,(int,float)) else '未列')+'；全职永久就业率 '+(str(ft)+'%' if isinstance(ft,(int,float)) else '未列')
            salary='全职永久就业者 gross 月薪中位数 '+(f'{currency} {median:,}' if isinstance(median,(int,float)) else '未列')
            if isinstance(p25,(int,float)) and isinstance(p75,(int,float)):salary+='；P25–P75 '+f'{currency} {p25:,}–{p75:,}'
            detail='官方 '+cohort+' 调查；'+summary+'。'+salary+'。适用范围：'+item.get('country_of_employment_scope','原调查范围')+'。'+item.get('interpretation_limit','')
            cards.append(E(label+' · '+cohort+': '+summary+'；'+salary+'。仅代表原调查届别与国家/地区口径，不代表中国就业、个人结果或未来预测。'))
            refs.append(eid)
    return cards,sorted(set(refs))


def scoped_school_pages(report,school,program,evidence,today,reference_only=False):
    """Keep university-wide scores; use reviewed programme examples on page 3."""
    s=copy.deepcopy(school)
    value=program_value(program,'career_detail_reference',evidence,today)
    detail=career_detail_page(program,evidence,today)
    if detail and not value.get('preserve_existing_school_examples'):
        # A reviewed programme example does not depend on a complete legacy
        # university dossier. Keep the six school-wide dimensions unknown.
        if not s.get('deep'):
            s['deep']={'overview':[(label,'待采集','没有已核全校事实；专业学习实例不替代该维度。','')
                for label in ('中国学生规模','国内校友组织','商界影响力','传播可见度','公共领域','公益与行业社群')]}
        d=s['deep'];d['abcnotes']=[(x['label'],x['display'],x['note'],'') for x in value['cards']]
        d['scale']={'title':'本专业学习与职业实例','note':'校友六维为全校口径；以下为本专业独立案例。','labels':[],'values':[]}
        d['details']=[(x['label'],x['display'],x['note']) for x in value['cards']]
        d['action']=value.get('boundary','实例不等于录取或就业承诺。');d['detailrefs']=''
    extra=links(detail[1],evidence) if detail else ''
    class ScopedReport:
        def page(self,title,sub,body,sources='',tag=''):
            status='资料对照，非本次推荐' if reference_only else '已列入自动角色，仍按条件三态核验'
            return report.page(title,sub+' · '+status,body,(sources+' · '+extra).strip(' ·'),tag)
    school_pages(ScopedReport(),s)


def build(form_path,out,as_of,scenario=None,pdf=True,comparison=None):
    tick=time.perf_counter()
    if out.exists():raise ValueError('使用全新目录，禁止覆盖学生产物')
    raw=read_form(form_path)
    extras={k:raw.get(k) for k in ('地区优先顺序','按国际自费学费估算')}
    clean={k:v for k,v in raw.items() if k not in extras}
    profile=normalize(clean)
    if isinstance(profile,tuple):profile=profile[0]
    if 'profile' in profile:profile=profile['profile']
    # Validate optional explicit ordering; an unordered region list is not a ranking.
    priority=extras['地区优先顺序'] or []
    if not isinstance(priority,list) or any(not isinstance(v,str) for v in priority):raise ValueError('地区优先顺序须为明确的地区列表')
    allowed=profile.get('preferences',{}).get('study_regions',[])
    if allowed!=['不限'] and any(v not in allowed for v in priority):raise ValueError('地区优先顺序包含未申报可接受地区')
    today=dt.date.fromisoformat(as_of)
    paths={k:ROOT/'database/v2'/f'{k}.json' for k in ('programs','evidence','taxonomy','jobs','direction_registry')}
    paths['universities']=ROOT/'database/universities.json'
    paths['school_evidence']=ROOT/'database/evidence.json'
    hashes={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()}
    programs=read(paths['programs']);evidence={e['id']:e for e in read(paths['evidence'])};taxonomy=read(paths['taxonomy'])
    registered={r['major_id'] for r in read(paths['direction_registry'])['directions']}
    routes=propose_routes(profile,taxonomy);mids={mid for route in routes['routes'] for mid in route['major_ids']}
    if not mids<=registered:raise ValueError('专业尚未注册通用流程')
    selected_programs=[p for p in programs if set(p['major_ids'])&mids]
    comparison_ids=comparison_scope(comparison,programs,mids)
    source='form-sha256:'+hashlib.sha256(form_path.read_bytes()).hexdigest()
    screenings=[];transcripts={};tuition={};mapping_notes={}
    for p in selected_programs:
        facts,notes=map_program(p,profile,source);transcripts[p['id']]=facts;mapping_notes[p['id']]=notes
        with submitted_input_mode():
            screen=screen_program(p,profile,evidence,facts,False,today,scenario)
        screen['input_basis']='self_reported_not_independently_verified'
        screen['personal_fit_confirmed']=False
        t=program_value(p,'tuition',evidence,today)
        # Subsidised/conditional foreign-student rates require separate acceptance.
        conditional=t and ('grant' in json.dumps(t).lower() or 'subsid' in json.dumps(t).lower())
        scope=extras['按国际自费学费估算'] is True and not conditional
        tuition[p['id']]=tuition_reference(p,profile,evidence,today,scenario,scope)
        screen['gates']['tuition_reference']={k:v for k,v in tuition[p['id']].items() if k not in ('value','cny_range','fx')}
        screen['state']=combine([v for k,v in screen['gates'].items() if k!='catalog'])['state']
        screen['label']=LABEL[screen['state']]+'（材料未独立核验）'
        screenings.append(screen)
    pool=select_candidates(selected_programs,screenings,mids,profile['student_id'],lambda p,k:program_value(p,k,evidence,today))
    benchmarks=[read(p) for p in (ROOT/'database/v2/subject_benchmarks').glob('*.json')]
    roles={g['major_id']:select_roles(g,selected_programs,screenings,evidence,today,benchmarks,priority,profile) for g in pool['majors']}
    matched_at=time.perf_counter()
    out.mkdir(parents=True)
    dump(out/'原始表格.json',raw);dump(out/'标准档案.json',profile);dump(out/'自动转录_未独立核验.json',transcripts)
    result={'student_id':profile['student_id'],'as_of':as_of,'routes':routes,'screenings':screenings,'candidate_pools':pool,
            'roles':roles,'tuition':tuition,'mapping_notes':mapping_notes,'source_hashes':hashes,
            'input_basis':'self_reported_not_independently_verified','independent_verification_completed':False,
            'synthetic':str(profile['student_id']).startswith('SYNTHETIC'), 'four_role_method':'automatic_data_driven_with_explicit_ties',
            'comparison_program_ids':comparison_ids,'comparison_is_recommendation':False,
            'limitation':'初筛指南；不是录取承诺或经独立核验的精准适配。未知项仍需核验。'}
    dump(out/'自动匹配结果.json',result)
    snapshot=out/'输入存档';snapshot.mkdir()
    for key,path in paths.items():(snapshot/('school_evidence.json' if key=='school_evidence' else path.name)).write_bytes(path.read_bytes())
    dump(snapshot/'费用情景.json',scenario)
    dump(snapshot/'学科标杆.json',benchmarks)
    dump(snapshot/'资料对照范围.json',comparison)
    report=Report(profile['identity'].get('姓名',profile['student_id'])+' · 自动匹配留学指南',
                  profile['student_id']+' / 学生填报初筛',as_of)
    majors={m['id']:m['name'] for m in taxonomy['majors']};by={p['id']:p for p in programs}
    scr={s['program_id']:s for s in screenings}
    ident=profile['identity'];family=profile.get('family_context',{})
    budget=family.get('annual_budget_cny')
    body='<div class="band"><div><h2>'+E(ident.get('姓名') or profile['student_id'])+'</h2><p>'+E(ident.get('课程体系'))+' · '+E(ident.get('入学年月'))+'</p></div><div class="hero">个人初筛</div></div>'
    body+='<div class="grid two">'+card('学生意向',' / '.join(majors[m] for m in sorted(mids)) or '待确认','从本人填写的方向检索本科项目')+card('家长年度预算',f'{budget/10000:g}万元' if budget is not None else '待确认','未用家长职业或学历推算预算')+card('可接受地区',' / '.join(allowed) or '待确认','家长许可：'+' / '.join(family.get('allowed_regions',[])))+card('本人明确优先顺序',' → '.join(priority) or '未指定','无明确顺序时，不按表格排列替学生决定')+'</div>'
    body+='<div class="callout">'+('合成测试学生，非真实申请案例。' if result['synthetic'] else '')+'成绩按填报值进行条件比较；证明材料尚未独立核验。明确不满足会排除，缺资料显示待核。</div>'
    report.page('先看孩子，再看学校','01 / 履历一览 · 学生与家长信息分开',body,tag='个人画像')
    portrait=profile.get('portrait',[])
    if isinstance(portrait,dict):portrait=list(portrait.values())
    states=['有填报' if d.get('status') in ('self_reported','submitted_unverified') else '待补' for d in portrait][:6]
    states+=['待补']*(6-len(states))
    body='<div class="split"><div>'+wheel(states)+'</div><div>'
    for d in portrait[:6]:body+='<div class="row"><b>'+E(d.get('name'))+'</b><p>'+E('；'.join(d.get('observations',[]))[:95] or '待补材料，不代表能力差')+'</p></div>'
    body+='</div></div><div class="callout">短问卷形成六维证据画像，不编造能力分、家庭资源分或录取概率。</div>'
    report.page('六维画像，已知与未知分开','02 / 学术 · 竞赛 · 自主学习 · 协作 · 语言 · 兴趣',body,tag='六维画像')
    selected_ids=[];gaps=[('问卷转档','需确认',x) for x in profile.get('warnings',[])+profile.get('gaps',[])]
    role_names={'global':'全球专业标杆参考','asia':'亚洲专业标杆参考','fit':'精准匹配 · 综合候选','asia_fit':'亚洲实际匹配 · 候选'}
    for mid in sorted(mids):
        body='<div class="grid two">'
        for key,role in roles[mid].items():
            chosen=role['selected'];pid=chosen['program_id'] if chosen else None
            if pid:
                selected_ids.append(pid);school=BY.get(by[pid]['school_id'],{})
                value=school.get('name',by[pid]['school_id'])
                detail=chosen['label']+'。'+role['reason']
                if key in ('global','asia'):detail+='；个人条件：'+LABEL[chosen['condition_state']]
                labels=[x['label'] for x in chosen.get('reason_breakdown',{}).get('feature_evidence',[])]
                if labels:detail+='；课程兴趣关联：'+'、'.join(dict.fromkeys(labels))
            else:
                value='暂不强选';detail=role['reason']+'；候选数 '+str(len(role['alternatives']))
            body+=card(role_names[key],value,detail,'asia highlight' if key=='asia_fit' else 'asia' if key=='asia' else 'highlight' if key=='fit' else '')
        body+='</div><div class="callout">自动从当前已入库项目选择，未使用固定四校名单。标杆展示学科实力，不等于符合学生条件；候选并非已确认适合。</div>'
        rank_refs=[ref for role in roles[mid].values() for ref in ((role.get('selected') or {}).get('rank_evidence') or {}).get('evidence_ids',[])]
        report.page(majors[mid]+'：四个位置自动生成','专业方向 / 亚洲双推荐与个人匹配分别判断',body,links(rank_refs,evidence),tag='精准匹配 / 亚洲双推荐')
    # Optional direction dossier is separate from automatic recommendations.
    selected_ids=list(dict.fromkeys(selected_ids))
    display_ids=list(dict.fromkeys(selected_ids+comparison_ids))
    if comparison_ids:
        for part in chunks(comparison_ids,4):
            body='<div class="grid two">'
            for pid in part:
                p=by[pid];state=scr[pid]['state'];name=BY.get(p['school_id'],{}).get('name',p['school_id'])
                label=('自动角色已选 / ' if pid in selected_ids else '资料对照，非推荐 / ')+LABEL[state]
                body+=card(name,program_value(p,'official_name',evidence,today) or p.get('degree_key') or pid,label+'；原政策年 '+str(p.get('policy_year')))
            body+='</div><div class="callout">四校资料完整展示与自动选校是两回事：对照名单不参与打分或补位。不满足、并列或待核的学校不会因此变成适合推荐。下文依次呈现申请、费用、就业与学校三页。</div>'
            report.page('同一方向，四校放在一起看','资料范围 / 为家长提供可追溯的比较依据',body,tag='方向资料总览')
    for pid in display_ids:
        p=by[pid];s=scr[pid];school=BY.get(p['school_id'],{});name=school.get('name',p['school_id'])
        gate_items=list(s['gates'].items());gaps.extend((name,GATE_NAMES.get(k,k),friendly_reason(k,v.get('reason',''))) for k,v in gate_items if v.get('state')=='unknown')
        groups=[('申请年份',['policy_year']),('学术与先修',['credential_requirements','subject_requirements','high_school_entry','international_eligible','degree_level','additional_requirements']),
                ('语言条件',['english_requirements']),('地区与学制',['student_region','parent_region','duration']),
                ('学费与年预算',['tuition_reference']),('完整费用与其他要求',['budget','standardised_tests','age_process'])]
        body='<div class="grid two">'
        for label,keys in groups:
            values=[s['gates'][k] for k in keys if k in s['gates']]
            combined=combine(values)
            detail='；'.join(GATE_NAMES[k]+'：'+LABEL[s['gates'][k]['state']] for k in keys if k in s['gates'])
            body+=card(label,LABEL[combined['state']],detail)
        body+='</div><div class="tiny">'+('资料对照，非本次推荐。' if pid not in selected_ids else '')+'通过仅表示填报值达到该项；证明材料尚未独立核验，不代表整体录取。全部逐项条件保留在随附数据中。</div>'
        report.page(name+'：六项条件一眼看清','录取与家庭条件 / 原政策年 '+str(p.get('policy_year')),body,tag='条件解释')
        admission_detail=admission_detail_page(p,evidence,today)
        if admission_detail:
            route_body,route_refs=admission_detail
            report.page(name+'：申请与主修怎么衔接','申请路径 / 已核流程与目标年度待核项分开',route_body,links(route_refs,evidence),tag='申请路径')
        preparation_detail=admission_detail_page(p,evidence,today,'application_preparation_reference')
        if preparation_detail:
            prep_body,prep_refs=preparation_detail
            report.page(name+'：考试与材料时间表','申请准备 / 已备材料不等于录取通过',prep_body,links(prep_refs,evidence),tag='申请准备')
        cost=tuition[pid];t=cost.get('value')
        body='<div class="grid two">'
        detail='原始年份、币种保持，不外推新学年'
        tuition_txt=f"{t.get('amount_min'):,.0f}–{t.get('amount_max'):,.0f} {t.get('currency')}" if t and isinstance(t.get('amount_min'),(int,float)) and isinstance(t.get('amount_max'),(int,float)) else '待核'
        body+=card('学费 / 原政策年 '+str(t.get('base_year') if t else '待核'),tuition_txt,detail)
        for key,label in [('living_cost','生活费'),('other_costs','杂费及其他')]:
            val=program_value(p,key,evidence,today)
            living=program_value(p,'living_cost',evidence,today)
            combined_living=isinstance(living,dict) and living.get('includes_other_expenses') is True
            if combined_living:label='生活及其他 · 校方指导' if key=='living_cost' else '尚未覆盖费用'
            if isinstance(val,dict) and isinstance(val.get('amount_min'),(int,float)):
                lo,hi=val['amount_min'],val.get('amount_max')
                amount=f'{lo:,.0f}' if hi==lo else f"{lo:,.0f}–{format(hi,',.0f') if isinstance(hi,(int,float)) else '上限待核'}"
                txt=amount+' '+val.get('currency','')
                note={'academic_year':'每学年','calendar_year':'每自然年','month':'每月'}.get(val.get('period'),str(val.get('period','')))+'；覆盖范围仍需核对'
                if val.get('official_estimate'):note+='；校方指导估算，非全年锁价'
            else:txt='待核';note='不以零元代替缺项'
            if combined_living and key=='other_costs':note='只补未覆盖项目，不重复叠加已含杂费'
            body+=card(label,txt,note)
        bounds=s['gates']['budget'].get('total_cny')
        body+=card('全学程合计',str(bounds) if bounds else '暂不能给完整合计','有完整分项才汇总；不足时保留缺口')+'</div>'
        if cost.get('cny_range'):body+='<div class="callout">学费约人民币 '+E('–'.join(f'{x/10000:.1f}万' for x in cost['cny_range']))+'；情景汇率 '+E(cost['fx'])+'，设定日 '+E((scenario or {}).get('fx_date','未标注'))+'，非实时汇率。'+E(cost['reason'])+'</div>'
        oneoffs,oneoff_refs=cost_reference_rows(p,evidence,today)
        body+=oneoffs+living_observations(p)
        source_ids=[i for key in ('tuition','living_cost','other_costs') for i in p.get('facts',{}).get(key,{}).get('evidence_ids',[])]+oneoff_refs
        report.page(name+'：费用分开看','预算 / 已核原年数值、规划情景与未知分列',body,links(source_ids,evidence),tag='费用预算')
        planning=cost_planning_page(p,evidence,today)
        if planning:
            planning_body,planning_refs=planning
            report.page(name+'：先准备多少费用','规划参考 / 学年小计与四年学费情景',planning_body,links(planning_refs,evidence),tag='费用规划')
        detail=cost_detail_page(p,evidence,today)
        if detail:
            detail_body,detail_refs=detail
            report.page(name+'：费用口径说明','校方参考 / 适用条件与未统一项目分开',detail_body,links(detail_refs,evidence),tag='费用核对')
            detail_value=program_value(p,'cost_detail_reference',evidence,today)
            gaps.extend((name,'费用口径待核',note) for note in detail_value.get('caveats',[]))
        career=career_detail_page(p,evidence,today)
        if career:
            career_body,career_refs=career
            report.page(name+'：这个专业能走向哪里','专业课程与校友实例 / 学校介绍不替代中国招聘条件',career_body,links(career_refs,evidence),tag='专业发展')
    jobs=read(paths['jobs'])
    for mid in sorted(mids):
        js=[j for j in jobs if any(x.get('major_id')==mid for x in j.get('major_links',[]))]
        for part_index,part in enumerate(chunks(js,4) or [[]]):
            body='<div class="grid two">';refs=[]
            for j in part:
                f=j['facts'];value=lambda k:f.get(k,{}).get('value') if f.get(k,{}).get('status')=='verified' else None
                title=value('title') or j['id'];employer=value('employer') or '雇主待核'
                salary=value('salary')
                salary_text=(salary.get('raw') or '数值/周期待核') if isinstance(salary,dict) else str(salary or '数值/周期待核')
                education=value('education');education_text='、'.join(education) if isinstance(education,list) else str(education or '待核')
                experience=value('experience')
                experience_text='、'.join(experience) if isinstance(experience,list) else str(experience or '待核')
                status_text=job_status_label(j,today)
                detail='学历：'+education_text+'；经验/条件：'+experience_text+'；薪酬：'+salary_text+'；'+status_text
                if isinstance(salary,dict) and (salary.get('tax_basis') in (None,'unknown') or salary.get('months') is None):detail+='；税前后/发薪月数待核'
                body+=card(employer,title,detail);refs+=f.get('title',{}).get('evidence_ids',[])
            body+='</div><div class="callout">本方向岗位样本 '+str(len(js))+' 条。样本用于了解招聘条件，不是热门专业平均薪资；缺计薪周期不换算年薪，无法据此承诺行业前20%收入。</div>'
            if part_index==0:
                outcome_cards,outcome_refs=historical_employment_cards(display_ids,by,mid,evidence)
                if outcome_cards:
                    body+='<div class="callout">院校历史毕业调查（独立口径，不计入中国岗位样本）：'+' '.join(outcome_cards[:2])+' 数据适用于原调查国家/地区，不代表中国就业或未来预测。</div>'
                    refs.extend(outcome_refs)
            report.page(majors[mid]+'：回国就业看真实岗位','岗位来源 / 历史公开样本不保证仍在招',body,links(refs,evidence),tag='回国就业')
    school_programs={}
    for pid in display_ids:school_programs.setdefault(by[pid]['school_id'],pid)
    for sid,pid in school_programs.items():
        if sid in BY:
            scoped_school_pages(report,BY[sid],by[pid],evidence,today,pid not in selected_ids)
            if comparison_ids:
                school=BY[sid];deep=school.get('deep') or {}
                gaps.extend((school['name'],'校友/ABC资料',x) for x in deep.get('remaining',[]))
                missing_dims=[label for label,score in zip(
                    ('中国学生规模','国内校友组织','商界影响力','传播可见度','公共领域','公益与行业社群'),
                    school.get('alumni_scores') or [None]*6) if score is None]
                if missing_dims:gaps.append((school['name'],'校友六维缺项','、'.join(missing_dims)+'仍待核；专业具名实例不替代全校维度。'))
                gaps.append((school['name'],'ABC原始指标','现有学校图为QS代理参照；完整原始ABC指标未核齐，不等于本专业排名。'))
        else:gaps.append((sid,'school_details','学校三页资料尚未接入'))
    for g in pool['majors']:
        if not g['programs']:gaps.append((majors[g['major_id']],'program_data','此方向尚无新版项目；不能从学校总库假造招生要求'))
        for role,r in roles[g['major_id']].items():
            if not r['selected']:gaps.append((majors[g['major_id']],role,r['reason']))
        for row in g['programs']:
            if row['bucket']=='excluded':gaps.append((BY.get(row['school_id'],{}).get('name',row['school_id']),'不满足项','、'.join(GATE_NAMES.get(k,k) for k in row['failed_conditions'])))
    for i,part in enumerate(chunks(gaps,7) or [[]]):
        body=''.join('<div class="row"><b>'+E(name)+' · '+E(key)+'</b><p>'+E(why)+'</p></div>' for name,key,why in part)
        report.page('待核与排除原因 '+str(i+1),'缺口独立列示 / 完整条件与来源另见自动匹配结果JSON',body,tag='缺口清单')
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[k] for k,p in paths.items()):raise RuntimeError('生成期间共享数据库变化，请新目录重试')
    cited_ids={i for pid in display_ids for fact in by[pid]['facts'].values() if isinstance(fact,dict) for i in fact.get('evidence_ids',[])}
    cited_ids.update(i for j in jobs if any(x.get('major_id') in mids for x in j.get('major_links',[])) for f in j['facts'].values() if isinstance(f,dict) for i in f.get('evidence_ids',[]))
    report.md+=['## 可点击来源索引（保留各条原年与适用范围）']
    report.md += [f"- [{eid}]({evidence[eid]['url']})：{evidence[eid].get('data_period','年份见原文')}；{evidence[eid].get('scope','')}" for eid in sorted(cited_ids) if eid in evidence and evidence[eid].get('url')]
    legacy=read(paths['school_evidence']).get('sources',{})
    legacy_ids=set()
    for sid in school_programs:
        d=BY.get(sid,{}).get('deep') or {}
        legacy_ids.update(d.get('detailrefs','').split())
        for row in d.get('overview',[])+d.get('abcnotes',[]):
            if len(row)>3:legacy_ids.update(row[3].split())
    report.md+=['## 学校三页的校级来源（不代表本专业适配）']
    report.md += [f"- [{eid} · {legacy[eid].get('title',eid)}]({legacy[eid]['url']})：复核日 {legacy[eid].get('accessed','未列')}" for eid in sorted(legacy_ids) if eid in legacy and legacy[eid].get('url')]
    prepared_at=time.perf_counter()
    report.save(out,pdf=pdf)
    finished_at=time.perf_counter()
    manifest={'student_id':profile['student_id'],'pages':len(report.pages),'elapsed_seconds':time.perf_counter()-tick,
              'database_hashes':hashes,'form_sha256':source,'pdf_generated':pdf,'independent_review':False,
              'selected_program_ids':selected_ids,'role_selection':'automatic','major_ids':sorted(mids),
              'comparison_program_ids':comparison_ids,'displayed_program_ids':display_ids,
              'phase_seconds':{'form_to_selection':matched_at-tick,'content_preparation':prepared_at-matched_at,'save_and_pdf':finished_at-prepared_at},
              'limitation':'程序初版；资料与未实现的规则保留未知。初筛成功不等于确认精准适配。'}
    dump(out/'生成记录.json',manifest)
    return manifest


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--form',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--history-dir',type=Path,help='Optional destination for generation timing records (defaults to the package task-management folder).')
    ap.add_argument('--as-of',required=True);ap.add_argument('--scenario',type=Path);ap.add_argument('--no-pdf',action='store_true');ap.add_argument('--comparison',type=Path)
    a=ap.parse_args()
    manifest=build(a.form,a.out,a.as_of,read(a.scenario) if a.scenario else None,not a.no_pdf,read(a.comparison) if a.comparison else None)
    from pipeline_optimization import record_generation
    record_generation(manifest,a.out,history_dir=a.history_dir)
    print(json.dumps(manifest,ensure_ascii=False))
