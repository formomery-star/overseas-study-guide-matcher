"""Normalize a short form into evidence-state portraits; not a psychometric score.

Accepts labelled Markdown or the equivalent flat JSON object. School records can
be supplied in JSON; unstructured grades stay verbatim until reviewed.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EMPTY={'','待定','待补','不确定','暂不确定','待确认','____','未填写'}
FIELDS={
 '学生编号','姓名','学校年级','毕业年月','入学年月','课程体系','毕业资格','学校所在地','国籍居留类别',
 '成绩材料状态','成绩说明','奖项状态','代表奖项','活动状态','代表活动','活动时长','本人职责','成果链接',
 '喜欢学科','不喜欢学科','愿意任务','不愿意任务','意向专业职业','主动学习内容','学习成果','遇阻处理',
 '合作角色','合作贡献','英语使用','英语场景','新环境行为','新环境场景','工作看重','留学地区','就业地点',
 '作品准备状态','作品链接','接受额外考核','执业地区','接受较长训练','特殊方向','不能接受',
 '年预算万元','总预算万元','依赖奖助','接受预科','父亲职业','母亲职业','实际支持','每月支持小时',
 '家长期望','家长可接受地区','亲子分歧','最长培养年数','IB各科目授课语言说明',
}
FIELD_ALIASES={'各IB科目授课语言说明':'IB各科目授课语言说明',
               'IB科目授课语言':'IB各科目授课语言说明'}
MATERIAL_STATES={'成绩材料状态':{'已附','学校统一提供','待补'},
                 '奖项状态':{'有且附证明','有，证明待补','无'},
                 '活动状态':{'有且附证明','有，证明待补','无'}}
TASKS={
 'A':('解题/分析数据',['science','computing','business']),
 'B':('写程序',['computing']),
 'C':('设计/搭装置',['engineering']),
 'D':('实验/观察自然',['science','health','environment']),
 'E':('阅读/写作/辩论',['humanities','society','media']),
 'F':('视觉设计/创作',['arts']),
 'G':('组织/商业策划',['business','service']),
 'H':('帮助/教学/照护',['education','health']),
 'I':('表演/音乐',['arts']),
 'J':('体育/户外',['service']),
 'K':('其他',[]),'L':('暂不确定',[]),
}
ABILITY_MAP={
 '学术基础':['学术硬实力'],'竞赛成果':['学术硬实力'],
 '自主学习':['学习底层能力'],'实践协作':['学习底层能力','性格与职业匹配'],
 '语言适应':['跨文化适配'],'兴趣职业':['性格与职业匹配'],
}

def text(value):
    if value is None:return ''
    if not isinstance(value,str):raise ValueError('文字字段应为字符串，不能把列表/数值直接拼成事实')
    value=value.strip()
    return '' if value in EMPTY or re.fullmatch(r'[_＿\s]*',value) else value

def tokens(value):
    if isinstance(value,list):return [text(x) for x in value if text(x)]
    value=text(value)
    return [x.strip() for x in re.split(r'[，,；;、\n]+',value) if x.strip() and x.strip() not in EMPTY]

def parse_markdown(content):
    # Unknown labels are reported, never silently interpreted as a different question.
    result={};unknown=[]
    for line in content.splitlines():
        match=re.match(r'^\s*(?:[-*]\s*)?([^#：:]{1,24})[：:]\s*(.*?)\s*$',line)
        if not match:continue
        key,value=match.groups();key=key.strip();key=FIELD_ALIASES.get(key,key)
        if key in FIELDS:
            if key in result:raise ValueError(f'重复字段：{key}；请保留唯一答案')
            result[key]=value
        else:unknown.append(key)
    if not result:raise ValueError('未识别到v2问卷字段；自由格式材料需要先整理，不能猜测转档')
    result['_unrecognized_labels']=unknown
    return result

def read_form(path):
    if path.suffix.lower()=='.docx':
        from questionnaire2form import convert
        raw,_=convert(path)
    else:
        content=path.read_text(encoding='utf-8-sig')
        if path.suffix.lower()=='.json':raw=json.loads(content)
        else:raw=parse_markdown(content)
    if not isinstance(raw,dict):raise ValueError('问卷须为一个对象')
    for alias,canonical in FIELD_ALIASES.items():
        if alias in raw:
            raw.setdefault(canonical,raw[alias]);raw.pop(alias)
    # A storage identity is not an admissions input. No student-facing ID question.
    if not text(raw.get('学生编号')):
        prefix='SYNTHETIC_Q_' if '合成' in str(raw.get('姓名','')) else 'Q_'
        raw['学生编号']=prefix+uuid.uuid4().hex
        raw['_internal_identity']={'generated':True,'purpose':'内部隔离与留档，不参与院校匹配','strategy':'uuid4'}
    return raw

def number(raw,key,warnings,factor=1):
    value=raw.get(key)
    if value is None or (isinstance(value,str) and not text(value)):return None
    if type(value) is bool:raise ValueError(f'{key}不能是布尔值')
    try:
        if isinstance(value,str) and not re.fullmatch(r'\d+(?:\.\d+)?',value.strip()):raise ValueError()
        n=float(value)
        if not 0<=n<1e12:raise ValueError()
        return n*factor
    except (TypeError,ValueError):
        warnings.append(f'{key}未识别为单一非负数字，保留原文并列待确认');return None

def normalize(raw,prior=None):
    warnings=[];gaps=[];prior=prior or {};raw=copy.deepcopy(raw)
    if not isinstance(raw,dict) or not isinstance(prior,dict):raise ValueError('输入/历史档案必须是对象')
    sid=text(raw.get('学生编号'))
    if not sid:raise ValueError('必须填写学生编号；避免把不同学生合并')
    if prior and prior.get('student_id')!=sid:raise ValueError('历史档案编号不一致，拒绝合并')
    def val(k):return text(raw.get(k))
    def seq(k):return tokens(raw.get(k))
    def dimension(name,status,observations,missing):
        return {'name':name,'ability_groups':ABILITY_MAP[name],'status':status,
                'observations':observations,'gaps':missing,'score':None,
                'interpretation':'资料与自报状态，不是能力高低或录取概率'}
    for key in raw.get('_unrecognized_labels',[]):warnings.append(f'未识别标签：{key}，需人工检查')
    for key in raw:
        if key not in FIELDS and key not in ('_unrecognized_labels','学术记录','奖项记录','活动记录','_internal_identity','_conversion'):
            warnings.append(f'未处理JSON字段：{key}，已保留原始输入')
    warnings.extend(raw.get('_conversion',{}).get('warnings',[]))
    evidence={};previous=prior.get('materials',{})
    for category,state_key,summary_key,record_key in [
        ('academic','成绩材料状态','成绩说明','学术记录'),
        ('awards','奖项状态','代表奖项','奖项记录'),
        ('activities','活动状态','代表活动','活动记录')]:
        state=val(state_key);summary=val(summary_key);records=raw.get(record_key,[])
        if not isinstance(records,list) or any(not isinstance(x,dict) for x in records):raise ValueError(f'{record_key}须为对象列表')
        for record in records:
            if 'verification' in record:record['reported_verification']=record.pop('verification')
            record['verification']='submitted_not_independently_checked'
        if state and state not in MATERIAL_STATES[state_key]:warnings.append(f'{state_key}选项未识别：{state}')
        if category=='academic':
            for record in records:
                # Preserve exact subjects, assessment types and grading scales; no AP equivalence assumptions.
                if not isinstance(record.get('subject'),str) or not record['subject'].strip():raise ValueError('学术记录缺准确科目名')
                if record.get('record_type') not in ('official','predicted','mock','school_grade','planned','unspecified'):
                    raise ValueError('学术记录须区分正式/预估/模考/校内/计划')
                if record.get('record_type')=='unspecified':gaps.append('学术记录成绩类型未注明，不能当成正式成绩')
                attendance=record.get('record_kind')=='test_attendance'
                if attendance:
                    if not record.get('exam_name') or not record.get('date'):
                        gaps.append('考试参加记录缺考试名或日期，参加状态待核')
                elif record.get('record_type')!='planned' and any(record.get(k) is None for k in ['value','scale','date']):
                    gaps.append('学术记录存在分值、满分制或日期缺失，不能判定学术资格')
        has=bool(summary or records)
        if state=='无' and has:
            status='conflict';warnings.append(f'{state_key}填无但又申报经历，需确认')
        elif has:status='submitted_unverified'
        elif state=='无':status='reported_none'
        elif state in ('已附','有且附证明','有，证明待补','学校统一提供'):status='pending_materials'
        else:status='pending' if category=='academic' else 'unreported'
        item={'status':status,'declared_status':state or None,'summary':summary or None,'records':records,
              'source':'current_form','carried_forward':False}
        old=previous.get(category)
        if old and (old.get('summary') or old.get('records')) and not has:
            item=copy.deepcopy(old);item.update(carried_forward=True,source='prior_profile',current_declared_status=state or None)
            if state=='无':item['status']='conflict';warnings.append(f'{state_key}与已有经历冲突；保留历史，不自动删除')
        evidence[category]=item
    liked=[];disliked=[]
    for key,target in [('愿意任务',liked),('不愿意任务',disliked)]:
        for code in seq(key):
            code=code.upper()
            if code not in TASKS:warnings.append(f'{key}未识别任务代码：{code}，不自动归类')
            elif code not in target:target.append(code)
    overlap=set(liked)&set(disliked)
    if overlap:warnings.append('任务偏好存在冲突：'+','.join(sorted(overlap)))
    if 'L' in liked and len(liked)>1:warnings.append('同时选择暂不确定和具体任务，需确认')
    if len(liked)>2 or len(seq('喜欢学科'))>3:warnings.append('偏好超过问卷建议数量，保留全部，不据此放大适配')
    family_signals={}
    for code in liked:
        if code in overlap:continue
        for fid in TASKS[code][1]:family_signals.setdefault(fid,[]).append({'task':code,'label':TASKS[code][0],'basis':'student_self_report'})
    learning=[f'{k}：{val(k)}' for k in ('主动学习内容','学习成果','遇阻处理') if val(k)]
    teamwork=[f'{k}：{val(k)}' for k in ('合作角色','合作贡献','本人职责','活动时长') if val(k)]
    language=[f'{k}：{val(k)}' for k in ('英语使用','英语场景','新环境行为','新环境场景') if val(k)]
    interests={'favorite_subjects':seq('喜欢学科'),'disliked_subjects':seq('不喜欢学科'),
               'liked_tasks':liked,'disliked_tasks':disliked,'explicit_directions':seq('意向专业职业'),
               'values':seq('工作看重'),'special_direction':val('特殊方向') or None,
               'unacceptable':val('不能接受') or None,'family_signals':family_signals}
    interest_obs=[f'喜欢学科：{", ".join(interests["favorite_subjects"])}'] if interests['favorite_subjects'] else []
    if liked:interest_obs.append('任务偏好：'+','.join(liked))
    if interests['explicit_directions']:interest_obs.append('本人意向：'+','.join(interests['explicit_directions']))
    # Interest tasks nominate broad exploration only; never force a program based on parents' occupations.
    academic=evidence['academic'];awards=evidence['awards'];activities=evidence['activities']
    academic_obs=[academic['summary']] if academic['summary'] else []
    academic_obs += [f"{r['subject']}：{r.get('value','待补')} / {r.get('scale','待补')}；{r.get('record_type')}；{r.get('date','日期待补')}" for r in academic.get('records',[])]
    portrait=[
        dimension('学术基础',academic['status'],academic_obs,['完整成绩单、课程级别、分制、日期、正式考试及预测成绩区分；材料需核验']),
        dimension('竞赛成果',awards['status'],[awards['summary']] if awards['summary'] else [],['有申报时核对主办方、奖级、年份和个人贡献'] if awards['status'] not in ('unreported','reported_none') else []),
        dimension('自主学习','self_reported' if learning else 'pending',learning,['自报行为需作品或教师观察验证；没有例子不判为能力低']),
        dimension('实践协作','self_reported' if teamwork else activities['status'],teamwork,['本人任务、持续时间、成果与合作过程需核实']),
        dimension('语言适应','self_reported' if language else 'pending',language,['正式语言成绩、版本、小分与有效期另核；英语考试不能替代跨文化适应经历']),
        dimension('兴趣职业','self_reported' if interest_obs else 'pending',interest_obs,['探索线索需学生试做反馈；不是经过验证的性格测验']),
    ]
    family={'annual_budget_cny':number(raw,'年预算万元',warnings,10000),'total_budget_cny':number(raw,'总预算万元',warnings,10000),
            'budget_source':'parent_report_unverified','scholarship_dependency':val('依赖奖助') or None,
            'foundation_acceptance':val('接受预科') or None,'father_occupation':val('父亲职业') or None,
            'mother_occupation':val('母亲职业') or None,'reported_support':seq('实际支持'),
            'support_hours_per_month':number(raw,'每月支持小时',warnings),'expectations':val('家长期望') or None,
            'allowed_regions':seq('家长可接受地区'),'disagreement':val('亲子分歧') or None,
            'max_duration_years':number(raw,'最长培养年数',warnings)}
    identity={k:val(k) or None for k in ('姓名','学校年级','毕业年月','入学年月','课程体系','毕业资格','学校所在地','国籍居留类别')}
    instruction_language=text(raw.get('IB各科目授课语言说明'))
    academic_instruction_languages={
        'status':'self_reported_not_independently_checked' if instruction_language else 'unreported',
        'value':instruction_language or None,
        'verified':False,
        'source':'current_form' if instruction_language else None,
        'scope':'仅保存学生对IB逐科授课语言的自报；未核验前不用于英语资格gate或豁免判定。'
    }
    for k in ['入学年月','课程体系','毕业资格']:
        if not identity[k]:gaps.append(k+'待确认')
    if family['annual_budget_cny'] is None and family['total_budget_cny'] is None:gaps.append('家庭预算待确认，不能判定费用适配')
    if not interest_obs:gaps.append('本人兴趣待确认，不能用父母职业代替')
    for k in ('作品准备状态','接受额外考核','执业地区','接受较长训练'):
        if not val(k):gaps.append(k+'按所选方向再确认')
    return {'schema_version':2,'student_id':sid,'identity':identity,'materials':evidence,'interests':interests,
            'learning':learning,'teamwork':teamwork,'language_and_adaptation':language,'family_context':family,
            'preferences':{'study_regions':seq('留学地区'),'work_location':val('就业地点') or None},
            'academic_instruction_languages':academic_instruction_languages,
            'special_requirements':{k:val(k) or None for k in ('作品准备状态','作品链接','接受额外考核','执业地区','接受较长训练')},
            'portrait':portrait,'warnings':warnings,'gaps':gaps,'raw_answers':raw,
            'handoff':{'profile_kind':'exploration_only','eligible_for_confirmed_fit':False,
                       'family_signal_ids':list(family_signals),'maximum_routes':3,'maximum_majors_per_route':2,
                       'reason':'只完成输入转档和证据画像；资格筛选、专业排名与院校匹配须由后续程序执行'}}

def render_md(profile):
    def safe(v):return str(v).replace('|','/').replace('\n',' / ')
    lines=['# 学生六维资料画像', '', f"学生编号：{safe(profile['student_id'])}", '',
           '本页显示资料状态，不生成能力分、录取概率或院校推荐。','',
           '| 六维 | 对应四大能力 | 资料状态 |','|---|---|---|']
    for d in profile['portrait']:lines.append(f"| {d['name']} | {'、'.join(d['ability_groups'])} | {d['status']} |")
    lines+=['','## 家庭与可行性（不计入孩子能力）','',f"每年预算人民币：{profile['family_context']['annual_budget_cny'] if profile['family_context']['annual_budget_cny'] is not None else '待确认'}",f"总预算人民币：{profile['family_context']['total_budget_cny'] if profile['family_context']['total_budget_cny'] is not None else '待确认'}",'', '## 待核与冲突','']
    lines+=['- '+safe(x) for x in profile['warnings']+profile['gaps']]
    for d in profile['portrait']:
        lines+=['', '## '+d['name'],'']+['- '+safe(x) for x in d['observations']+d['gaps']]
    return '\n'.join(lines)+'\n'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--form',type=Path,required=True);parser.add_argument('--prior',type=Path);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    prior=json.loads(args.prior.read_text(encoding='utf-8')) if args.prior else None
    result=normalize(read_form(args.form),prior)
    if args.out.exists() and any(args.out.iterdir()):raise SystemExit('拒绝覆盖已有学生输出目录，请用新版本目录')
    args.out.mkdir(parents=True,exist_ok=True)
    source=args.form.read_bytes();(args.out/('原始问卷'+args.form.suffix)).write_bytes(source)
    result['manifest']={'input_sha256':hashlib.sha256(source).hexdigest(),'generated_at':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
                        'prior_profile':str(args.prior.resolve()) if args.prior else None,'engine':'intake_v2'}
    (args.out/'标准档案.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (args.out/'六维资料画像.md').write_text(render_md(result),encoding='utf-8')
    print(json.dumps({'student_id':result['student_id'],'dimensions':len(result['portrait']),'warnings':len(result['warnings']),'output':str(args.out),'school_recommendations_generated':False},ensure_ascii=False))

if __name__=='__main__':main()
