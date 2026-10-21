import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import community_data as c


def sample():
    return {'schema_version':1, 'contribution_id':'synthetic-example', 'license':'CC0-1.0', 'changes':[
        {'program_id':'synthetic-cs-2027', 'field':'duration_years', 'expected_sha256':c.digest(None),
         'value':4, 'scope':'Synthetic only; not a university fact', 'evidence':{
             'id':'synthetic-evidence', 'url':'https://example.org/program', 'publisher':'Synthetic University',
             'source_type':'university_official', 'checked_on':dt.date.today().isoformat(),
             'data_period':'2027 synthetic', 'scope':'synthetic', 'summary':'Fixture only; not verified real information'}}]}


class ContributionTests(unittest.TestCase):
    def test_valid_submission_is_not_approved(self):
        self.assertEqual(c.validate(sample())['status'], 'awaiting_review')

    def test_invalid_inputs(self):
        for value in (None, '', -1, 'four', True, 11, float('nan')):
            with self.subTest(value=value):
                p=sample(); p['changes'][0]['value']=value
                with self.assertRaises(ValueError): c.validate(p)

    def test_no_review_flags_or_rules_from_contributor(self):
        p=sample(); p['changes'][0]['evidence']['reviewed_by']='self'
        with self.assertRaises(ValueError): c.validate(p)
        p=sample(); p['changes'][0]['field']='subject_requirements'
        with self.assertRaises(ValueError): c.validate(p)

    def test_missing_source_and_duplicate(self):
        p=sample(); p['changes'][0]['evidence']['url']=''
        with self.assertRaises(ValueError): c.validate(p)
        p=sample(); p['changes']*=2
        with self.assertRaises(ValueError): c.validate(p)

    def test_fee_identity(self):
        p=sample(); p['changes'][0]['field']='tuition'; p['changes'][0]['value']={'amount':100}
        with self.assertRaises(ValueError): c.validate(p)

    def test_stage_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); base=root/'base'; base.mkdir()
            c.write_new(base/'programs.json',[{'id':'synthetic-cs-2027','facts':{}}])
            c.write_new(base/'evidence.json',[])
            before=(base/'programs.json').read_bytes()
            p=sample(); approval=c.review(p,'test-maintainer','Synthetic workflow test only')
            m=c.stage(p,approval,base,root/'v1')
            self.assertEqual(m['status'],'staged_not_deployed')
            self.assertEqual((base/'programs.json').read_bytes(),before)
            self.assertEqual(c.read(root/'v1/programs.json')[0]['facts']['duration_years']['value'],4)
            with self.assertRaises(FileExistsError): c.stage(p,approval,base,root/'v1')
            with self.assertRaises(ValueError): c.stage(p,approval,root/'v1',root/'v2')
            changed=copy.deepcopy(p); changed['changes'][0]['value']=3
            with self.assertRaises(ValueError): c.stage(changed,approval,base,root/'v3')
            unknown=sample(); unknown['changes'][0]['program_id']='unknown'
            with self.assertRaises(ValueError): c.stage(unknown,c.review(unknown,'test','test'),base,root/'v4')


if __name__ == '__main__': unittest.main()
