"""Conservative cross-major screening prototype. No admission probabilities.







Verified program facts and separate reviewed student facts are required. Missing,



stale, unsupported, or ambiguous rules remain UNKNOWN. Production PDF integration



and subject-rank role selection are separate, unfinished tasks.



"""



import argparse



import datetime as dt



import hashlib



import json



import math



from contextvars import ContextVar



from contextlib import contextmanager



from pathlib import Path



import re



import validate_v2 as catalog



import qualification_sets



import application_materials



import age_conditions



import readiness_v2



import science_entry_rules







ROOT=Path(__file__).resolve().parents[1]



PASS='satisfied';FAIL='not_satisfied';UNKNOWN='unknown'



_SUBMITTED_INPUT = ContextVar('submitted_input', default=False)







@contextmanager



def submitted_input_mode():



    """Explicit provisional evaluation; never changes stored verification status."""



    token=_SUBMITTED_INPUT.set(True)



    try:yield



    finally:_SUBMITTED_INPUT.reset(token)







def result(state,reason,**extra):return dict(state=state,reason=reason,**extra)



def numeric(v):return type(v) in (int,float) and math.isfinite(v)



def combine(items,mode='all'):



    if not items:return result(UNKNOWN,'空条件不能证明满足')



    states=[r['state'] for r in items]



    if mode=='all':state=FAIL if FAIL in states else UNKNOWN if UNKNOWN in states else PASS



    else:state=PASS if PASS in states else UNKNOWN if UNKNOWN in states else FAIL



    return result(state,'逐条条件合并',checks=items)







def reviewed_value(fact):



    allowed=('verified','self_reported') if _SUBMITTED_INPUT.get() else ('verified',)



    if not isinstance(fact,dict) or fact.get('status') not in allowed or not fact.get('source_refs') or not fact.get('scope'):



        return None,False



    return fact.get('value'),fact.get('value') is not None







def evaluate_rule(rule,student_facts,reference_date=None):



    if not isinstance(rule,dict):return result(UNKNOWN,'没有可执行条件')



    op=rule.get('op')



    if op=='policy_pending':



        return result(UNKNOWN,rule.get('reason') if isinstance(rule.get('reason'),str) and rule['reason'].strip() else '项目专项政策尚未核验')



    if op=='admission_test_participation':


        import admission_tests


        value,known=reviewed_value(student_facts.get(rule.get('field')))


        return admission_tests.participation(rule,value if known else None,reference_date)


    if op=='gcse_minimum':



        if not isinstance(rule.get('field'),str):return result(UNKNOWN,'GCSE成绩字段未定义')



        value,known=reviewed_value(student_facts.get(rule.get('field')))



        if not known:return result(UNKNOWN,'GCSE成绩或等同资格待核；不从雅思推定通过')



        return science_entry_rules.secondary(value,reference_date,rule.get('mathematics_minimum'),rule.get('english_language_minimum'))



    if op in ('science_grade_profile','science_subject_profile','al_subject_minimum','al_subject_mix'):



        if not isinstance(rule.get('field'),str):return result(UNKNOWN,'科学项目成绩字段未定义')



        value,known=reviewed_value(student_facts.get(rule['field']))



        if not known:return result(UNKNOWN,'完整实得成绩尚未核验')



        if op=='science_grade_profile':return science_entry_rules.credential(rule,value,reference_date)



        if op=='al_subject_minimum':return science_entry_rules.al_subject_minimum(rule,value,reference_date)



        if op=='al_subject_mix':return science_entry_rules.al_subject_mix(rule,value,reference_date)



        review,reviewed=reviewed_value(student_facts.get(rule.get('review_field')))



        secondary,secondary_known=reviewed_value(student_facts.get(rule.get('secondary_field')))



        return science_entry_rules.subjects(rule,value,review if reviewed else None,secondary if secondary_known else None,reference_date)



    if op=='route_select':



        field=rule.get('field');cases=rule.get('cases')



        if (not isinstance(field,str) or not isinstance(cases,dict) or not cases



                or any(not isinstance(k,str) or not k or not isinstance(v,dict) for k,v in cases.items())):



            return result(UNKNOWN,'已核路径选择规则格式待核')



        value,known=reviewed_value(student_facts.get(field))



        if not known or not isinstance(value,str) or value not in cases:



            return result(UNKNOWN,'路径未核验或尚未实现；不能据此否定其他可用资格')



        answer=evaluate_rule(cases[value],student_facts,reference_date)



        answer['selected_route']=value



        return answer



    if op=='credential_scope':



        field=rule.get('field');allowed=rule.get('values')



        if not isinstance(field,str) or not isinstance(allowed,list) or not allowed:



            return result(UNKNOWN,'学历适用范围格式待核')



        value,known=reviewed_value(student_facts.get(field))



        if not known or value not in allowed:



            return result(UNKNOWN,'学历未确认或不在此条规则的已核范围，需其他路径')



        return evaluate_rule(rule.get('rule'),student_facts,reference_date)



    if op=='ib_subject_minimum':



        if not isinstance(rule.get('field'),str) or not isinstance(rule.get('selection_field'),str):



            return result(UNKNOWN,'IB成绩或科目审阅字段未定义')



        value,known=reviewed_value(student_facts.get(rule['field']))



        selection,selected=reviewed_value(student_facts.get(rule['selection_field']))



        if not known or not selected:return result(UNKNOWN,'IB完整成绩及项目科目认定须分别核验')



        return qualification_sets.ib_subject_minimum(rule,value,selection,reference_date)



    if op=='ib_diploma':



        if not isinstance(rule.get('field'),str):return result(UNKNOWN,'IB材料字段未定义')



        value,known=reviewed_value(student_facts.get(rule['field']))



        return qualification_sets.ib_diploma(rule,value,reference_date) if known else result(UNKNOWN,'IB完整成绩未独立核验')



    if op in ('ap_set','exam_attempts'):



        if not isinstance(rule.get('field'),str):return result(UNKNOWN,'考试材料字段未定义')



        value,known=reviewed_value(student_facts.get(rule['field']))



        if not known:return result(UNKNOWN,'考试材料尚未独立核验：'+rule['field'])



        cutoff=None



        if op=='exam_attempts':



            if not isinstance(rule.get('valid_on_field'),str):return result(UNKNOWN,'考试有效期截止日字段待核')



            cutoff,known=reviewed_value(student_facts.get(rule['valid_on_field']))



            if not known:return result(UNKNOWN,'该学历申请截止日未独立核验')



        return qualification_sets.evaluate(rule,value,reference_date,cutoff)



    if op in ('all','any'):



        items=rule.get('items')



        if not isinstance(items,list):return result(UNKNOWN,'组合条件格式待核')



        combined=combine([evaluate_rule(x,student_facts,reference_date) for x in items],op)



        pending=[x.get('reason') for x in items if isinstance(x,dict) and x.get('op')=='policy_pending' and isinstance(x.get('reason'),str)]



        if combined['state']==UNKNOWN and pending:combined['reason']='；'.join(pending)



        return combined



    if op=='none_required':



        return result(PASS,'官方已确认无此项要求') if rule.get('basis') else result(UNKNOWN,'无要求仍需明确依据')



    if op not in ('eq','in','gte','lte','exam') or not isinstance(rule.get('field'),str):



        return result(UNKNOWN,'不支持的条件类型，需补规则；不猜测')



    value,known=reviewed_value(student_facts.get(rule['field']))



    if not known:return result(UNKNOWN,'学生事实未独立核验：'+rule['field'])



    if op=='eq':



        expected=rule.get('value')



        if expected is None or type(value) is not type(expected):return result(UNKNOWN,'值类型或预期值不明确')



        return result(PASS if value==expected else FAIL,'精确等值比较：'+rule['field'])



    if op=='in':



        options=rule.get('values')



        if not isinstance(options,list) or not options:return result(UNKNOWN,'允许值列表缺失')



        return result(PASS if any(type(value) is type(x) and value==x for x in options) else FAIL,'资格范围比较：'+rule['field'])



    if op in ('gte','lte'):



        expected=rule.get('value')



        if not numeric(value) or not numeric(expected):return result(UNKNOWN,'数值或分制不能自动比较')



        ok=value>=expected if op=='gte' else value<=expected



        return result(PASS if ok else FAIL,'数值条件：'+rule['field'])



    # One exam attempt is an indivisible object: never combine sections from different sittings.



    if not isinstance(value,dict):return result(UNKNOWN,'考试记录必须是一场完整考试')



    required=('name','version','record_type','minimum','scale','valid_on','max_age_days')



    if any(k not in rule for k in required):return result(UNKNOWN,'考试名称/版本/分制/有效期要求缺失')



    for key in ('name','version','record_type','scale'):



        if key not in value:return result(UNKNOWN,'考试记录缺少'+key)



        if type(value[key]) is not type(rule[key]) or value[key]!=rule[key]:return result(UNKNOWN,'考试类型/版本/分制不一致；需匹配相应规则')



    exam_date=catalog.valid_date(value.get('date'));valid_on=catalog.valid_date(rule.get('valid_on'))



    if not exam_date or not valid_on or not numeric(rule['max_age_days']) or rule['max_age_days']<0:



        return result(UNKNOWN,'考试日期或有效期无法核对')



    if reference_date and valid_on<reference_date:return result(UNKNOWN,'考试有效期检查基准已过，需要复核')



    if not 0<=(valid_on-exam_date).days<=rule['max_age_days']:return result(FAIL,'该考试不在要求的有效期内')



    minimum=rule.get('minimum');score=value.get('overall')



    if not numeric(score) or not numeric(minimum):return result(UNKNOWN,'考试总分待核')



    checks=[result(PASS if score>=minimum else FAIL,'考试总分')]



    section_rules=rule.get('sections',{})



    if not isinstance(section_rules,dict):return result(UNKNOWN,'考试小分规则格式待核')



    sections=value.get('sections',{})



    if not isinstance(sections,dict):return result(UNKNOWN,'考试分项记录格式待核')



    for section,threshold in section_rules.items():



        actual=sections.get(section)



        checks.append(result(UNKNOWN,'小分待核：'+section) if not numeric(actual) or not numeric(threshold)



                      else result(PASS if actual>=threshold else FAIL,'考试小分：'+section))



    return combine(checks)







def program_value(program,key,evidence,today):



    f=program.get('facts',{}).get(key,{})



    refs=f.get('evidence_ids')



    if f.get('status')!='verified' or not isinstance(refs,list) or not refs or not f.get('scope'):



        return None



    for ref in refs:



        e=evidence.get(ref,{})



        checked=catalog.valid_date(e.get('checked_on'))



        if (e.get('source_type') not in ({'university_official','government'} if key in ('immigration_cost_reference','cost_detail_reference','career_detail_reference') else {'university_official'}) or not e.get('reviewed_by') or



                not checked or not 0<=(today-checked).days<=90):return None



    return f.get('value')







REGIONS={'英国':'GB','美国':'US','加拿大':'CA','中国香港':'HK','香港':'HK','新加坡':'SG',



         '日本':'JP','韩国':'KR','澳大利亚':'AU','澳洲':'AU','新西兰':'NZ','中国内地':'CN',



         '德国':'DE','法国':'FR','荷兰':'NL','瑞士':'CH','爱尔兰':'IE','意大利':'IT','西班牙':'ES'}







def region_gate(country,choices):



    if not choices:return result(UNKNOWN,'留学地区尚未确认')



    if not country:return result(UNKNOWN,'项目所在国家/地区未核验')



    if choices==['不限']:return result(PASS,'明确不限地区')



    codes=[REGIONS.get(x,x if x in REGIONS.values() else None) for x in choices]



    if country in codes:return result(PASS,'符合已填写地区')



    if None in codes:return result(UNKNOWN,'存在未解析的地区偏好，需确认而非排除')



    return result(FAIL,'不在已填写的地区范围')







def budget_gate(program,profile,evidence,today,scenario):



    family=profile.get('family_context',{});annual=family.get('annual_budget_cny');total=family.get('total_budget_cny')



    if annual is None and total is None:return result(UNKNOWN,'家庭预算未提供')



    if any(v is not None and (not numeric(v) or v<0) for v in (annual,total)):return result(UNKNOWN,'预算不是有效非负金额')



    years=program_value(program,'duration_years',evidence,today)



    if not numeric(years) or years<=0 or years!=int(years):return result(UNKNOWN,'实际学制待核或分数学制需另行计算')



    if not isinstance(scenario,dict) or not isinstance(scenario.get('fx_cny'),dict):



        return result(UNKNOWN,'需明确规划汇率情景')



    growth_by_component=scenario.get('annual_growth_by_component',{})



    if not isinstance(growth_by_component,dict):return result(UNKNOWN,'分项涨幅格式无效')



    projections=scenario.get('base_year_projection',{})



    if not isinstance(projections,dict) or set(projections)-{'tuition','living_cost','other_costs'}:



        return result(UNKNOWN,'费用基年推算情景格式无效')



    annual_lows=[0.0]*int(years);annual_highs=[0.0]*int(years);components=[]



    unbounded=False



    costs={key:program_value(program,key,evidence,today) for key in ('tuition','living_cost','other_costs')}



    coverage_gaps=catalog.cost_coverage_gaps(costs)



    if coverage_gaps:



        answer=result(UNKNOWN,'费用覆盖尚未核清，不能确认预算')



        answer['coverage_gaps']=coverage_gaps



        return answer



    for key in ('tuition','living_cost','other_costs'):



        cost=costs[key]



        if not isinstance(cost,dict):return result(UNKNOWN,'费用缺项：'+key)



        period=cost.get('period')



        schedule_errors=catalog.payment_schedule_errors(cost,key,years)



        if schedule_errors:return result(UNKNOWN,'支付安排待核：'+key+' / '+', '.join(schedule_errors))



        # Annual tuition is billed for an academic year, not twelve months of living.



        if key=='tuition' and period=='academic_year':multiplier=1



        elif period=='payment_schedule':multiplier=1



        elif period in ('calendar_year','month') and cost.get('coverage_months')==12:



            multiplier=12 if period=='month' else 1



        else:



            return result(UNKNOWN,'费用尚非全年口径，不能按全年总预算放行：'+key)



        lo,hi=cost.get('amount_min'),cost.get('amount_max')



        lower_only=hi is None and cost.get('bound_type')=='lower_only'



        if not numeric(lo) or lo<0 or (not lower_only and (not numeric(hi) or hi<lo)):



            return result(UNKNOWN,'费用区间无效：'+key)



        fx=1 if cost.get('currency')=='CNY' else scenario['fx_cny'].get(cost.get('currency'))



        if not numeric(fx) or fx<=0:return result(UNKNOWN,'对应币种规划汇率缺失')



        base=cost.get('base_year');target=program.get('policy_year')



        if type(base) is not int or type(target) is not int:



            return result(UNKNOWN,'费用基年与政策年必须明确')



        # Default preserves the previous explicitly supplied scenario, never defaults to zero.



        mode=cost.get('fee_mode','scenario_growth')



        if mode=='cohort_fixed':



            if cost.get('cohort_year')!=program.get('policy_year'):



                return result(UNKNOWN,'固定届别费用缺少一致的入学届别：'+key)



            growth=0



        elif mode=='scenario_growth':



            growth=growth_by_component.get(key,scenario.get('annual_growth'))



            if not numeric(growth) or not 0<=growth<=1:



                return result(UNKNOWN,'需明确有效的分项规划涨幅：'+key)



        else:return result(UNKNOWN,'未知费用调整方式：'+key)



        projection=projections.get(key);factor=1.0



        if base!=target:



            if (mode!='scenario_growth' or not 0<target-base<=10 or not isinstance(projection,dict)



                    or type(projection.get('from_year')) is not int or type(projection.get('to_year')) is not int



                    or projection['from_year']!=base or projection['to_year']!=target



                    or not isinstance(projection.get('basis'),str) or not projection['basis'].strip()



                    or not numeric(projection.get('annual_growth')) or not 0<=projection['annual_growth']<=1):



                return result(UNKNOWN,'需逐项明确从已核基年到政策年的推算假设，不能改写原报价：'+key)



            factor=(1+projection['annual_growth'])**(target-base)



        elif projection is not None:



            return result(UNKNOWN,'同年费用不接受多余的基年推算：'+key)



        nominal_lows=[lo*multiplier]*int(years)



        nominal_highs=None if lower_only else [hi*multiplier]*int(years)



        if period=='payment_schedule':



            nominal_lows=[0.0]*int(years);nominal_highs=None if lower_only else [0.0]*int(years)



            for payment in cost['payments']:



                nominal_lows[payment['year_index']]+=payment['amount_min']



                if nominal_highs is not None:nominal_highs[payment['year_index']]+=payment['amount_max']



        try:



            lows=[value*fx*factor*(1+growth)**n for n,value in enumerate(nominal_lows)]



            highs=None if nominal_highs is None else [value*fx*factor*(1+growth)**n for n,value in enumerate(nominal_highs)]



        except OverflowError:return result(UNKNOWN,'费用计算溢出：'+key)



        if any(not numeric(x) for x in lows+(highs or [])):



            return result(UNKNOWN,'费用计算溢出：'+key)



        for n in range(int(years)):



            annual_lows[n]+=lows[n]



            if highs is not None:annual_highs[n]+=highs[n]



        unbounded=unbounded or lower_only



        components.append({'component':key,'cny_low':lows[0],'cny_high':None if highs is None else highs[0],



                           'fee_mode':mode,'applied_annual_growth':growth,'annual_cny_low':lows,



                           'annual_cny_high':highs,'original_period':period,'annual_multiplier':multiplier})



        components[-1]['excluded_covered_by']=cost.get('excluded_covered_by',{})



        components[-1].update(source_base_year=base,planning_year=target,base_year_projection=projection,



                             is_projected=base!=target,payments=cost.get('payments'))



    totals=[sum(annual_lows),None if unbounded else sum(annual_highs)]



    peak=[max(annual_lows),None if unbounded else max(annual_highs)]



    if any(v is not None and not numeric(v) for v in totals+peak):



        return result(UNKNOWN,'汇总费用计算溢出')



    checks=[]



    for label,cap,bounds in [('每年预算',annual,peak),('全学程预算',total,totals)]:



        if cap is None:continue



        # An upper bound is necessary for a positive affordability decision.



        # Preserve incomplete ranges as unknown even if the known floor is high.



        state=UNKNOWN if bounds[1] is None else FAIL if bounds[0]>cap else PASS if bounds[1]<=cap else UNKNOWN



        checks.append(result(state,label+'缺上限，不能确认预算' if bounds[1] is None else label+'与费用范围比较'))



    if family.get('scholarship_dependency') not in ('否','不依赖'):



        checks.append(result(UNKNOWN,'奖助依赖未否定或尚未确认，不提前扣除奖学金'))



    answer=combine(checks);answer.update(components=components,total_cny=totals,peak_annual_cny=peak,duration_years=years,



        annual_cny_low=annual_lows,annual_cny_high=None if unbounded else annual_highs,



        scenario=scenario,budget_basis='planning_scenario_not_quote',



        note='情景预算；第1学年含赴学前付款，非日历年；一次性款仅计指定期；保留费用原始年份；缺项/上限未知不放行；未扣未获得奖助')



    return answer







def screen_program(program,profile,evidence,student_facts,catalog_ready,today,scenario=None):



    gates={'catalog':result(PASS if catalog_ready else UNKNOWN,'本科项目完整性校验')}



    year_match=re.fullmatch(r'(\d{4})-(0[1-9]|1[0-2])',str(profile.get('identity',{}).get('入学年月','')))



    year=int(year_match.group(1)) if year_match else None



    gates['policy_year']=result(PASS if year is not None and year==program.get('policy_year') else UNKNOWN,'必须核对目标入学年度，不能把旧政策当新政策')



    for key in ('high_school_entry','international_eligible'):



        value=program_value(program,key,evidence,today)



        gates[key]=result(UNKNOWN if type(value) is not bool else PASS if value else FAIL,key)



    level=program_value(program,'degree_level',evidence,today)



    gates['degree_level']=result(UNKNOWN if level is None else PASS if level in ('bachelor','integrated_undergraduate') else FAIL,'本科/高中直入学位层级')



    for key in ('credential_requirements','subject_requirements','english_requirements','additional_requirements'):



        value=program_value(program,key,evidence,today)



        gates[key]=evaluate_rule(value.get('rule'),student_facts,today) if year==program.get('policy_year') and isinstance(value,dict) and value.get('rule_version')==1 else result(UNKNOWN,'政策年度不符、未核验或未转成可执行规则：'+key)



    if 'standardised_tests' in program.get('facts',{}):



        value=program_value(program,'standardised_tests',evidence,today)



        gates['standardised_tests']=evaluate_rule(value.get('rule'),student_facts,today) if year==program.get('policy_year') and isinstance(value,dict) and value.get('rule_version')==1 else result(UNKNOWN,'标准化考试年度/证据/执行规则待核')



    if 'age_policy_reference' in program.get('facts',{}):



        value=program_value(program,'age_policy_reference',evidence,today)



        rule=value.get('rule') if isinstance(value,dict) else None



        gates['age_process']=result(UNKNOWN,'年龄政策年度、来源或学生年龄/签证材料待核')



        if year==program.get('policy_year') and isinstance(value,dict) and value.get('rule_version')==1 and isinstance(rule,dict) and rule.get('op')=='leeds_age_process' and isinstance(rule.get('field'),str):



            packet,known=reviewed_value(student_facts.get(rule['field']))



            if known and isinstance(packet,dict) and packet.get('program_id')==program['id'] and type(packet.get('policy_year')) is int and packet['policy_year']==year:



                gates['age_process']=age_conditions.check(packet,year,today)



    country=program_value(program,'country_code',evidence,today)



    gates['student_region']=region_gate(country,profile.get('preferences',{}).get('study_regions',[]))



    # Missing parent's region approval is not assumed agreement.



    gates['parent_region']=region_gate(country,profile.get('family_context',{}).get('allowed_regions',[]))



    duration=program_value(program,'duration_years',evidence,today);cap=profile.get('family_context',{}).get('max_duration_years')



    gates['duration']=result(PASS,'未设置明确培养年限上限') if cap is None else result(UNKNOWN,'学制/上限待核') if not numeric(cap) or not numeric(duration) else result(PASS if duration<=cap else FAIL,'培养年限对照')



    gates['budget']=budget_gate(program,profile,evidence,today,scenario)



    overall=combine(list(gates.values()))



    preparation=result(UNKNOWN,'政策年度、材料清单或独立审阅记录待核',admission_effect='none')



    value=program_value(program,'additional_requirements',evidence,today)



    if year==program.get('policy_year') and isinstance(value,dict):



        rule=value.get('preparation_checklist')



        packet,known=reviewed_value(student_facts.get(rule.get('field'))) if isinstance(rule,dict) and isinstance(rule.get('field'),str) else (None,False)



        preparation=application_materials.checklist(rule,packet if known else None,program['id'],year,today)



    return {'program_id':program['id'],'school_id':program['school_id'],'state':overall['state'],'gates':gates,



            'application_preparation':preparation,



            'label':'条件筛查通过（非录取承诺）' if overall['state']==PASS else '现有条件不满足' if overall['state']==FAIL else '待补证据，不能确认匹配',



            'admission_probability':None}







def propose_routes(profile,taxonomy):



    majors=taxonomy['majors'];by_id={m['id']:m for m in majors};names={m['name']:m['id'] for m in majors}



    groups={};unresolved=[];explicit=profile.get('interests',{}).get('explicit_directions',[])



    if explicit:



        for value in explicit:



            mid=value if value in by_id else names.get(value)



            if mid is None:unresolved.append(value);continue



            m=by_id[mid];groups.setdefault(m['family_id'],[])



            if mid not in groups[m['family_id']]:groups[m['family_id']].append(mid)



    else:



        # Task preferences yield families only; no arbitrary first two subjects within a family.



        for fid in profile.get('interests',{}).get('family_signals',{}):groups[fid]=[]



    routes=[];deferred=[]



    for fid,mids in groups.items():



        row={'family_id':fid,'major_ids':mids[:2],'status':'student_interest_exploration' if mids else 'family_exploration_needs_major_confirmation'}



        if len(routes)<3:routes.append(row)



        else:deferred.append(row)



        unresolved.extend(mids[2:])



    return {'routes':routes,'unresolved_directions':unresolved,'deferred_routes':deferred,



            'note':'明确意向用准确专业名/代码；未解析项不自动回退计算机，不按父母职业补意向'}







def load_student_review(path,profile_path,profile,today):



    if not path:return {},'未提供独立审阅记录，所有学术事实保持未知'



    packet=catalog.read(path)



    expected=hashlib.sha256(profile_path.read_bytes()).hexdigest()



    if packet.get('student_id')!=profile.get('student_id') or packet.get('profile_sha256')!=expected:



        raise ValueError('核验文件学生ID或档案哈希不匹配')



    checked=catalog.valid_date(packet.get('reviewed_on'))



    if not checked or checked>today or not packet.get('reviewer') or not isinstance(packet.get('facts'),dict):



        raise ValueError('核验文件缺审阅人、有效日期或事实对象')



    return packet['facts'],'已加载与此版档案绑定的审阅记录；需保证原始材料审阅真实'







def main():



    ap=argparse.ArgumentParser();ap.add_argument('--profile',type=Path,required=True);ap.add_argument('--review',type=Path)



    ap.add_argument('--scenario',type=Path);ap.add_argument('--as-of');ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()



    today=dt.date.fromisoformat(args.as_of) if args.as_of else dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()



    profile=catalog.read(args.profile)



    if profile.get('schema_version')!=2 or not profile.get('student_id'):raise ValueError('只接受intake_v2标准档案')



    facts,note=load_student_review(args.review,args.profile,profile,today)



    scenario=catalog.read(args.scenario) if args.scenario else None



    quality=catalog.validate(ROOT,str(today));ready={r['id'] for r in quality['records']['programs'] if r['ready']}



    route_data=propose_routes(profile,catalog.read(ROOT/'database/v2/taxonomy.json'))



    mids={m for r in route_data['routes'] for m in r['major_ids']}



    evidence={e['id']:e for e in catalog.read(ROOT/'database/v2/evidence.json')}



    programs=catalog.read(ROOT/'database/v2/programs.json')



    screenings=[screen_program(p,profile,evidence,facts,p['id'] in ready,today,scenario)



                for p in programs if set(p['major_ids'])&mids]



    quality_by_id={r['id']:r for r in quality['records']['programs']}



    for screening in screenings:



        screening['stage_diagnostics']=readiness_v2.screening_stages(screening)



        screening['evidence_diagnostics']=readiness_v2.evidence_stages(quality_by_id[screening['program_id']],quality['valid'])



    result_data={'as_of':str(today),'student_id':profile['student_id'],'routes':route_data,'screenings':screenings,



                 'passed_screenings':sum(r['state']==PASS for r in screenings),'catalog_valid':quality['valid'],



                 'catalog_errors':quality['errors'],'student_review':note,'global_asia_fit_selections':None,



                 'recommendation_policy':catalog.read(ROOT/'database/recommendation_policy.json'),



                 'production_pdf_generated':False,'note':'规则筛查原型；专业标杆排序、校友与图文正式输出尚未接通'}



    from candidate_selection_v2 import select_candidates



    result_data['automatic_candidate_pools']=select_candidates(programs,screenings,mids,profile['student_id'],



        lambda p,k:program_value(p,k,evidence,today))



    tracked={'profile':args.profile,'programs':ROOT/'database/v2/programs.json','evidence':ROOT/'database/v2/evidence.json',



             'taxonomy':ROOT/'database/v2/taxonomy.json','contract':ROOT/'database/v2/contract.json',



             'matcher':Path(__file__),'catalog_validator':ROOT/'scripts/validate_v2.py'}



    tracked['qualification_sets']=ROOT/'scripts/qualification_sets.py'



    tracked['science_entry_rules']=ROOT/'scripts/science_entry_rules.py'



    tracked['application_materials']=ROOT/'scripts/application_materials.py'



    tracked['age_conditions']=ROOT/'scripts/age_conditions.py'



    tracked['readiness_diagnostics']=ROOT/'scripts/readiness_v2.py'



    tracked['candidate_selector']=ROOT/'scripts/candidate_selection_v2.py'



    tracked['recommendation_policy']=ROOT/'database/recommendation_policy.json'



    if args.review:tracked['student_review']=args.review



    if args.scenario:tracked['cost_scenario']=args.scenario



    result_data['manifest']={k:{'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for k,p in tracked.items()}



    if args.out.exists() and any(args.out.iterdir()):raise SystemExit('拒绝覆盖已有筛选结果，请新建输出版本')



    args.out.mkdir(parents=True,exist_ok=True)



    (args.out/'筛选结果.json').write_text(json.dumps(result_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')



    lines=['# 跨专业条件筛查（开发版）','',f"学生编号：{profile['student_id']}",'','尚未生成正式院校推荐；通过筛查不代表录取。','']



    lines += ['## 自动候选池（所有方向共用；不是最终四校名单）','',



              '| 专业 | 条件通过 | 待核候选 | 不满足排除 | 身份待核 | 亚洲通过/待核 |','|---|---|---|---|---|---|']



    for group in result_data['automatic_candidate_pools']['majors']:



        pools=group['pools'];asia=group['asia_pools']



        lines += [f"| {group['major_id']} | {len(pools['condition_passed'])} | {len(pools['pending'])} | {len(pools['excluded'])} | {len(pools['identity_pending'])} | {len(asia['condition_passed'])}/{len(asia['pending'])} |"]



    lines += ['', '名单与逐项原因见筛选结果.json的automatic_candidate_pools；顺序为项目编号，不是适配排名。', '']



    for r in screenings:



        lines += ['## '+r['program_id'],'',r['label'],'','### 分层看进度（局部满足不等于整体匹配）','',



                  '| 层面 | 当前状态 |','|---|---|']



        stages=r['stage_diagnostics']



        lines += [f"| {stages[k]['label']} | {stages[k]['state']} |" for k in ('admissions','family_constraints','budget','catalog')]



        lines += ['| 正式图文报告 | v2尚未接通 |','','### 资料缺口','',



                  '| 资料组 | 状态 | 待核项 |','|---|---|---|']



        lines += [f"| {v['label']} | {v['state']} | {'；'.join(v['gaps']) or '该组无字段缺口；仍需看整体复核'} |"



                  for v in r['evidence_diagnostics']['stages'].values()]



        lines += ['','### 具体条件','', '| 条件 | 状态 | 原因 |','|---|---|---|']



        lines += [f"| {k} | {v['state']} | {v['reason']} |" for k,v in r['gates'].items()]



        lines += ['']



        prep=r['application_preparation']



        lines += ['### 申请材料准备（不计入录取判断）','',prep['reason'],'','| 材料 | 准备情况 |','|---|---|']



        lines += [f"| {x['label']} | {x['state']} |" for x in prep.get('items',[])]



        lines += ['','附加条件待核：'+'；'.join(prep.get('pending_conditions',[])),'']



    if not screenings:lines+=['目前意向未对应已入库的具体本科项目，需补库或确认专业名称。']



    (args.out/'筛选说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')



    print(json.dumps({'screened':len(screenings),'passed':result_data['passed_screenings'],'out':str(args.out)},ensure_ascii=False))







if __name__=='__main__':main()



