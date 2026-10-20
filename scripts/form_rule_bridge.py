"""Map standard form records to rule operands, preserving self-report provenance.

No fuzzy subject equivalence or fabricated independent subject review. Unsupported
routes/packets remain absent so the existing engine returns unknown.
"""
import copy


def explicit_qualification(profile):
    value=profile.get('identity',{}).get('毕业资格')
    aliases={'美国高中毕业文凭','us high school diploma','american high school diploma','us_high_school_diploma'}
    return 'US_HIGH_SCHOOL_DIPLOMA' if isinstance(value,str) and value.strip().casefold() in aliases else value


def canonical_records(profile):
    records=profile.get('materials',{}).get('academic',{}).get('records',[])
    packets={}; notes=[]
    total=[r for r in records if r.get('subject')=='IB Total' and r.get('scale')==45]
    core=[r for r in records if r.get('subject')=='IB Core' and r.get('scale')==3]
    subjects=[r for r in records if r.get('system')=='IB' and r.get('level') in ('HL','SL')]
    if len(total)==1 and len(core)==1:
        t=total[0]
        packets['ib']={'qualification':'IB_DIPLOMA','complete':t.get('complete'),
            'diploma_awarded':t.get('diploma_awarded'),'record_type':'achieved' if t.get('record_type')=='official' else t.get('record_type'),
            'result_basis':t.get('result_basis'),'session':t.get('session'),'issued_on':t.get('date'),
            'total':t.get('value'),'core_points':core[0].get('value'),
            'subjects':[{'subject':r['subject'],'level':r['level'],'score':r.get('value'),'session':r.get('session')} for r in subjects]}
        # Mixed predicted/actual records are not promoted by the total row.
        if any(r.get('record_type')!='official' for r in subjects+[core[0]]):packets['ib']['record_type']='mixed_or_predicted'
    elif total or subjects:notes.append('IB需唯一总分、核心分与完整六科；摘要不自动当完整成绩单')
    al=[r for r in records if r.get('system')=='UK_GCE_A_LEVEL']
    if al:
        t=al[0]
        packets['al']={'qualification':'UK_GCE_A_LEVEL','complete':all(r.get('complete') is True for r in al),
            'record_type':'achieved' if all(r.get('record_type')=='official' for r in al) else 'predicted_or_mixed',
            'result_basis':t.get('result_basis'),'session':t.get('session'),'issued_on':t.get('date'),
            'subjects':[dict({'subject':r['subject'],'grade':r.get('value'),'session':r.get('session')},
                             **({'practical_pass':r['practical_pass']} if 'practical_pass' in r else {})) for r in al]}
    # Transfer explicit GCSE 9–1 results only. Never infer an equivalence from
    # IELTS/IB or combine ambiguous duplicate and mixed-session records.
    gcse=[r for r in records if r.get('system')=='GCSE_9_1']
    selected={name:[r for r in gcse if r.get('subject')==name]
              for name in ('Mathematics','English Language')}
    if gcse:
        if all(len(rows)==1 for rows in selected.values()):
            rows=[selected[name][0] for name in selected]
            if (all(r.get('scale')==9 and r.get('complete') is True and r.get('record_type')=='official' for r in rows)
                    and isinstance(rows[0].get('date'),str) and rows[0]['date']==rows[1].get('date')
                    and isinstance(rows[0].get('session'),str) and rows[0]['session']==rows[1].get('session')):
                packets['gcse']={'qualification':'GCSE_9_1','complete':True,'record_type':'achieved',
                    'issued_on':rows[0]['date'],'mathematics':rows[0].get('value'),'english_language':rows[1].get('value')}
            else:notes.append('GCSE数学/英语须为同场实得9–1数制；未支持的组合待核')
        else:notes.append('GCSE数学与英语Language记录缺失或重复；不选择有利分数')
    exams=[]
    for r in records:
        if r.get('exam_name'):
            exams.append({'name':r['exam_name'],'version':r.get('version'),'scale':r.get('scale'),
                          'overall':r.get('value'),'score':r.get('value'),'sections':r.get('sections',{}),
                          'date':r.get('date'),'record_type':'achieved' if r.get('record_type')=='official' else r.get('record_type'),
                          'delivery':r.get('delivery'),'result_basis':r.get('result_basis'),
                          'valid_on':r.get('valid_on'),'valid_on_basis':r.get('valid_on_basis'),'complete':r.get('complete'),
                          'admission_cycle':r.get('admission_cycle'),'attempt_history_complete':r.get('attempt_history_complete')})
    packets['exams']=exams
    ap=[r for r in records if r.get('system')=='AP']
    if ap:
        from ap_transcription import canonical_subject
        packets['ap']={'complete':all(r.get('complete') is True for r in ap),
            'attempts':[{'name':'AP','subject':canonical_subject(r.get('subject_key') or r['subject']),
                'score':r.get('value'),'scale':r.get('scale'),'date':r.get('date'),
                'session':r.get('session'),'record_type':'achieved' if r.get('record_type')=='official' else r.get('record_type')} for r in ap]}
        notes.append('AP只核对项目已定义的考试组合；不自动认定高中毕业资格或替代IB/A-level')
    return packets,notes


def map_program(program,profile,source_ref):
    packets,notes=canonical_records(profile);facts={};conflicts=set()
    def put(key,value):
        if not isinstance(key,str) or value is None or key in conflicts:return
        item={'value':copy.deepcopy(value),'status':'self_reported','source_refs':[source_ref],
              'scope':'学生表格自动转录，仅按填报值初筛；未独立核验'}
        if key in facts and facts[key]['value']!=value:
            conflicts.add(key);facts.pop(key,None);notes.append('字段映射冲突：'+key)
        else:facts[key]=item
    def walk(rule):
        if not isinstance(rule,dict):return
        op=rule.get('op');field=rule.get('field')
        if op=='route_select':
            cases=rule.get('cases',{});choices=[]
            for key,child in cases.items():
                if key=='IB_DIPLOMA_FINAL_3HL' and packets.get('ib'):choices.append(key)
                if key=='IB_DIPLOMA' and packets.get('ib'):choices.append(key)
                if key=='IB_ENGLISH' and packets.get('ib'):choices.append(key)
                if key=='UK_GCE_A_LEVEL_FINAL_3' and packets.get('al'):choices.append(key)
                if key=='A_LEVEL' and packets.get('al'):choices.append(key)
                if key=='US_HIGH_SCHOOL_DIPLOMA' and explicit_qualification(profile)==key:choices.append(key)
                # Only exact exam type and delivery with an executable exam rule.
                for e in packets['exams']:
                    if e['name'] in ('IELTS Academic','IELTS UKVI Academic') and key.startswith(e['name']+' / '):
                        suffix=key.split(' / ',1)[1]
                        if (suffix in ('single test centre','test_centre') and e['delivery']=='test_centre') or (suffix=='online' and e['delivery']=='online'):
                            if e['result_basis']=='single_sitting':choices.append(key)
                    if key=='IELTS_ACADEMIC' and e['name']=='IELTS Academic' and e['delivery']=='test_centre' and e['result_basis']=='single_sitting':
                        choices.append(key)
            choices=sorted(set(choices))
            if len(choices)==1:put(field,choices[0]);walk(cases[choices[0]])
            else:notes.append('资格/考试路径未唯一识别：'+str(field))
        elif op=='credential_scope':
            qualification=explicit_qualification(profile)
            # AP enrolment alone is not proof of an American diploma.
            if qualification in rule.get('values',[]):
                put(field,qualification);walk(rule.get('rule'))
            else:notes.append('毕业资格未明确对应项目路径：'+str(field))
        elif op in ('ib_diploma','ib_subject_minimum'):
            put(field,packets.get('ib'))
            # selection_field is a distinct independent review, never synthesized.
        elif op=='gcse_minimum':
            records=profile.get('materials',{}).get('academic',{}).get('records',[])
            alternatives=rule.get('unimplemented_alternative_subjects',[])
            has_alternative=any(r.get('subject') in alternatives for r in records)
            packet=packets.get('gcse')
            if has_alternative and (not packet or not isinstance(packet.get('mathematics'),(int,float)) or packet['mathematics']<rule.get('mathematics_minimum',9)):
                notes.append('已填其他数学资格；适用性未实现，不按GCSE低分直接排除')
            else:put(field,packet)
        elif op in ('science_grade_profile','science_subject_profile','al_subject_minimum','al_subject_mix'):
            put(field,packets.get('ib') if rule.get('route')=='IB_DIPLOMA_FINAL_3HL' else packets.get('al') if rule.get('route')=='UK_GCE_A_LEVEL_FINAL_3' else None)
            if op=='science_subject_profile':put(rule.get('secondary_field'),packets.get('gcse'))
        elif op=='ap_set':
            put(field,packets.get('ap'))
        elif op=='admission_test_participation':
            es=[e for e in packets['exams'] if e['name']==rule.get('name')]
            if es:put(field,{'attempts':es})
        elif op=='exam_attempts':
            es=[e for e in packets['exams'] if e['name']==rule.get('name')]
            if es:
                put(field,{'complete':all(e['complete'] is True for e in es),'attempts':es})
                cutoffs={e['valid_on'] for e in es if isinstance(e.get('valid_on'),str)}
                if len(cutoffs)==1:put(rule.get('valid_on_field'),next(iter(cutoffs)))
        elif op in ('all','any'):
            for child in rule.get('items',[]):walk(child)
        # Equality date constraints are not auto-filled from the desired answer.
    for key in ('credential_requirements','subject_requirements','english_requirements','additional_requirements','standardised_tests'):
        value=program.get('facts',{}).get(key,{}).get('value')
        if isinstance(value,dict):walk(value.get('rule'))
    return facts,notes
