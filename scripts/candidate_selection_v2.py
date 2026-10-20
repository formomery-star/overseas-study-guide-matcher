"""Shared candidate pools for every major; no manual school lists or ranking claims.

Consumes existing three-state screening. Full catalog quality is reported separately
from student conditions. Pending candidates are never promoted to confirmed fit.
"""
from collections import Counter

PASS = 'satisfied'
FAIL = 'not_satisfied'
UNKNOWN = 'unknown'
ASIA = frozenset('AF AM AZ BH BD BT BN KH CN CY GE IN ID IR IQ IL JP JO KZ KW KG LA LB MY MV MN MM NP KP OM PK PS PH QA SA SG KR LK SY TW TJ TH TL TR TM AE UZ VN YE HK MO'.split())
REQUIRED = ('policy_year', 'high_school_entry', 'international_eligible',
            'degree_level', 'credential_requirements', 'subject_requirements',
            'english_requirements', 'additional_requirements', 'student_region',
            'parent_region', 'duration', 'budget')


def select_candidates(programs, screenings, major_ids, student_id, verified_value):
    """verified_value(program, key) must enforce source/date verification upstream.

    Return all pools, sorted by stable identifiers ONLY (not suitability). Keeping
    all options avoids arbitrary selection of the first school when evidence ties.
    """
    program_ids = [p['id'] for p in programs]
    screen_ids = [s['program_id'] for s in screenings]
    if len(set(program_ids)) != len(program_ids) or len(set(screen_ids)) != len(screen_ids):
        raise ValueError('重复项目或筛查ID，拒绝以末条覆盖前条')
    by_id = {p['id']: p for p in programs}
    if set(screen_ids) - set(by_id):
        raise ValueError('筛查引用了未提供的项目')
    by_screen = {s['program_id']: s for s in screenings}
    groups = []
    for major in sorted(set(major_ids)):
        rows = []
        # Different policy editions of one degree are references, not competing schools.
        # Keep every screening visible, including current-edition failures; an old
        # unknown edition must never bypass a current-edition rejection.
        exact_editions = {}
        def route_key(p):
            parts = (p.get('school_id'), p.get('degree_key'), p.get('campus_key'))
            return parts if all(isinstance(x, str) and x.strip() and 'pending' not in x.lower() and 'unknown' not in x.lower() for x in parts) else None
        for p in programs:
            if major not in p.get('major_ids', []):
                continue
            key = route_key(p)
            screen = by_screen.get(p['id'], {})
            if (key and screen.get('gates', {}).get('policy_year', {}).get('state') == PASS
                    and verified_value(p, 'official_name')
                    and verified_value(p, 'degree_level') in ('bachelor', 'integrated_undergraduate')):
                exact_editions.setdefault(key, []).append(p['id'])
        explicit_successors = {}
        for successor in programs:
            if major not in successor.get('major_ids', []):
                continue
            if by_screen.get(successor['id'], {}).get('gates', {}).get('policy_year', {}).get('state') != PASS:
                continue
            if not verified_value(successor, 'official_name') or verified_value(successor, 'degree_level') not in ('bachelor', 'integrated_undergraduate'):
                continue
            for previous_id in successor.get('previous_policy_program_ids', []):
                previous = by_id.get(previous_id, {})
                if (major in previous.get('major_ids', []) and previous_id != successor['id']
                        and all(previous.get(k) == successor.get(k) and previous.get(k)
                                for k in ('school_id', 'degree_key', 'campus_key'))):
                    explicit_successors.setdefault(previous_id, []).append(successor['id'])
        for p in sorted(programs, key=lambda p: p['id']):
            if major not in p.get('major_ids', []):
                continue
            screen = by_screen.get(p['id'])
            if screen and screen.get('school_id') != p['school_id']:
                raise ValueError('筛查学校ID与项目不一致')
            gates = dict((screen or {}).get('gates', {}))
            for key in REQUIRED:
                gates.setdefault(key, {'state': UNKNOWN, 'reason': '尚无该层筛查结果'})
            conditions = {k: v for k, v in gates.items() if k != 'catalog'}
            failed = [k for k, v in conditions.items() if v.get('state') == FAIL]
            unknown = [k for k, v in conditions.items() if v.get('state') not in (PASS, FAIL)]
            state = FAIL if failed else UNKNOWN if unknown else PASS
            identity_gaps = []
            name = verified_value(p, 'official_name')
            degree = verified_value(p, 'degree_level')
            if not isinstance(name, str) or not name.strip():
                identity_gaps.append('official_name')
            if degree not in ('bachelor', 'integrated_undergraduate'):
                identity_gaps.append('undergraduate_degree_identity')
            country = verified_value(p, 'country_code')
            bucket = ('excluded' if failed else 'identity_pending' if identity_gaps
                      else 'pending' if unknown else 'condition_passed')
            superseded_by = (sorted(set(exact_editions.get(route_key(p), []) + explicit_successors.get(p['id'], [])))
                             if gates['policy_year'].get('state') != PASS else [])
            if superseded_by:
                bucket = 'historical_reference'
            rows.append({'superseded_by': superseded_by, 'program_id': p['id'], 'school_id': p['school_id'],
                         'official_name': name, 'country_code': country,
                         'asia': country in ASIA if isinstance(country, str) else None,
                         'condition_state': state, 'bucket': bucket,
                         'failed_conditions': failed, 'unknown_conditions': unknown,
                         'identity_gaps': identity_gaps,
                         'catalog_quality': gates.get('catalog', {'state': UNKNOWN}),
                         'label': {'historical_reference': '其他政策年度参考；本申请年度已有同项目版本', 'excluded': '现有条件不满足', 'identity_pending': '项目身份待核，暂不上推荐卡',
                                   'pending': '待核候选', 'condition_passed': '条件筛查通过（非录取承诺）'}[bucket]})
        pools = {key: [r['program_id'] for r in rows if r['bucket'] == key]
                 for key in ('condition_passed', 'pending', 'excluded', 'identity_pending', 'historical_reference')}
        asia_pools = {key: [r['program_id'] for r in rows if r['bucket'] == key and r['asia'] is True]
                      for key in pools}
        groups.append({'major_id': major, 'programs': rows, 'pools': pools, 'asia_pools': asia_pools,
                       'school_ids_for_deduplicated_details': sorted({r['school_id'] for r in rows
                           if r['bucket'] in ('pending', 'condition_passed')}),
                       'coverage': 'in_catalog' if rows else 'no_programs_in_catalog',
                       'four_role_selection': None,
                       'selection_gap': '候选池已自动生成；标杆依据、候选优先顺序及四位置报告接线另行验收'})
    counts = Counter(r['bucket'] for g in groups for r in g['programs'])
    return {'schema_version': 1, 'student_id': student_id, 'majors': groups,
            'major_program_counts': dict(counts), 'order_basis': 'program_id_not_suitability',
            'personal_fit_confirmed': False, 'production_pdf_generated': False,
            'note': '所有专业共用同一筛选器；完整字段不是候选闸门；未知不补分、不强凑四校。计数为专业×项目，学校详情按学校去重。'}
