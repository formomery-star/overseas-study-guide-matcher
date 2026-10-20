"""Document preparation only; never an admission gate or quality assessment."""
import datetime as dt


def checklist(rule, packet, program_id, policy_year, today):
    answer = dict(state='unknown', reason='材料准备记录或规则待核', items=[],
                  admission_effect='none', quality_assessed=False,
                  additional_conditions_complete=False)
    if not isinstance(rule, dict) or rule.get('version') != 1:
        return answer
    required = rule.get('required_items')
    if (not isinstance(required, list) or not required
            or any(not isinstance(x, dict) or not isinstance(x.get('id'), str)
                   or not x['id'] or not isinstance(x.get('label'), str) for x in required)
            or len({x['id'] for x in required}) != len(required)):
        return answer
    answer['optional_supporting_documents'] = rule.get('optional_supporting_documents', [])
    answer['pending_conditions'] = rule.get('pending_conditions', [])
    valid = isinstance(packet, dict)
    if valid:
        try:
            reviewed = dt.date.fromisoformat(packet.get('reviewed_on', ''))
            valid = (packet.get('program_id') == program_id
                     and type(packet.get('policy_year')) is int
                     and packet['policy_year'] == policy_year
                     and isinstance(packet.get('reviewer'), str) and bool(packet['reviewer'].strip())
                     and 0 <= (today - reviewed).days <= 90
                     and isinstance(packet.get('items'), dict))
        except (TypeError, ValueError):
            valid = False
    items = packet['items'] if valid else {}
    for spec in required:
        item = items.get(spec['id'], {})
        state = 'unknown'
        if (isinstance(item, dict) and item.get('status') == 'verified'
                and isinstance(item.get('source_refs'), list) and item['source_refs']
                and all(isinstance(x, str) and x.strip() for x in item['source_refs'])
                and isinstance(item.get('scope'), str) and item['scope'].strip()):
            value = item.get('value')
            if isinstance(value, dict) and type(value.get('available')) is bool:
                state = 'prepared' if value['available'] else 'needs_preparation'
                allowed = spec.get('accepted_provenance')
                if state == 'prepared' and allowed and value.get('provenance') not in allowed:
                    state = 'unknown'
        answer['items'].append(dict(id=spec['id'], label=spec['label'], state=state))
    states = [x['state'] for x in answer['items']]
    answer['state'] = ('unknown' if 'unknown' in states else 'needs_preparation'
                       if 'needs_preparation' in states else 'listed_materials_prepared')
    answer['reason'] = '仅核已列材料可用性；不判断质量、学校接受、提交完成或录取适配'
    return answer
