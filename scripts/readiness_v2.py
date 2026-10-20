"""Explain independent evidence and student screening stages; never relax gates.

This is a diagnostic view, not another admission decision or a completion score.
Full catalog readiness and the matcher's overall state remain authoritative.
"""

GROUPS = {
    'identity': ('official_name', 'campus', 'degree_level', 'high_school_entry',
                 'international_eligible', 'duration_years', 'teaching_languages'),
    'admissions': ('credential_requirements', 'subject_requirements',
                   'english_requirements', 'additional_requirements'),
    'budget': ('tuition', 'living_cost', 'other_costs'),
    'career_path': ('licensure_path',),
}
LABELS = {'identity':'本科项目身份资料', 'admissions':'招生核心资料',
          'budget':'费用覆盖资料', 'career_path':'职业资格路径资料'}


def evidence_stages(record, catalog_valid):
    """Classify the existing validator's gaps, including future unknown gap types."""
    rid = record['id']
    groups = {k: [] for k in GROUPS}
    groups['review'] = []
    for gap in record.get('gaps', []):
        key = gap.removeprefix(rid + '.').split(':', 1)[0]
        target = next((k for k, fields in GROUPS.items() if key in fields), 'review')
        if key == 'undergraduate_degree_required':target = 'identity'
        # Cross-component collision or mapping errors belong to budget, not a
        # harmless review-only bucket (e.g. tuition/other_costs:duplicate...).
        if any(key.startswith(f + '/') for f in GROUPS['budget']):target = 'budget'
        groups[target].append(gap)
    blocked = not catalog_valid or bool(record.get('errors'))
    result = {}
    for name, gaps in groups.items():
        result[name] = {
            'label': LABELS.get(name, '整条资料复核'),
            'state': 'invalid' if blocked else 'incomplete' if gaps else 'documented',
            'gaps': gaps,
            'meaning': '仅字段证据状态；不代表规则可执行、学生符合或录取概率',
        }
    return {'stages': result, 'full_record_ready': bool(record.get('ready')) and not blocked,
            'errors': list(record.get('errors', [])), 'catalog_valid': catalog_valid}


def _group(gates, keys, label):
    states = [gates.get(k, {}).get('state', 'unknown') for k in keys]
    state = ('not_satisfied' if 'not_satisfied' in states else
             'satisfied' if states and all(s == 'satisfied' for s in states) else 'unknown')
    return {'label':label, 'state':state, 'gate_keys':list(keys),
            'unresolved': [k for k,s in zip(keys,states) if s != 'satisfied']}


def screening_stages(screening):
    """Read already evaluated gates; missing gates are unknown, never pass.

    Optional tests and age conditions are included when the matcher emitted them.
    Application preparation remains an independent non-admission checklist.
    """
    gates = screening.get('gates', {})
    admission = ['policy_year','high_school_entry','international_eligible','degree_level',
                 'credential_requirements','subject_requirements','english_requirements',
                 'additional_requirements']
    admission += [k for k in ('standardised_tests','age_process') if k in gates]
    return {
        'admissions': _group(gates,admission,'已实现招生条件筛查（非录取结论）'),
        'family_constraints': _group(gates,['student_region','parent_region','duration'],'学生与家庭约束'),
        'budget': _group(gates,['policy_year','budget'],'目标年度预算匹配'),
        'catalog': _group(gates,['catalog'],'完整项目资料验收'),
        'overall_state': screening.get('state','unknown'),
        'application_preparation': screening.get('application_preparation',{'state':'unknown'}),
        'production_report': {'state':'not_integrated',
                              'reason':'v2正式院校角色选择、校友与PDF输出尚未接通'},
        'note':'分层视图不修改任何筛查结果；局部满足不等于整体匹配，材料准备不代替录取条件。',
    }
