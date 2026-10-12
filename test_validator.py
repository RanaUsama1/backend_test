import json,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
from validate_taxonomy import audit
REFERENCE=Path(__file__).with_name('reference_human.zip')
class Tests(unittest.TestCase):
 def altered(self,change):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);p=Path(temp.name)/'changed.zip'
  with ZipFile(REFERENCE) as src,ZipFile(p,'w') as dst:
   for name in src.namelist():dst.writestr(name,change(name,src.read(name)))
  return audit(p,{'query':'9606','tax_id':'9606'})
 def test_reference(self):self.assertEqual(audit(REFERENCE,{'query':'9606'})['outcome'],'PASS')
 def test_source_corruption(self):
  r=self.altered(lambda n,b:b+b' ' if n=='sources/efetch.xml' else b);self.assertIn('efetch checksum',r['errors'])
 def test_missing_lineage(self):
  def change(n,b):
   if n!='normalized_metadata.json':return b
   d=json.loads(b);d['lineage']=[];return json.dumps(d)
  self.assertIn('all lineage entries',self.altered(change)['errors'])
 def test_broken_link(self):
  r=self.altered(lambda n,b:b+b'<a href="missing.xml">bad link</a>' if n=='report.html' else b);self.assertEqual(r['outcome'],'FAIL')
if __name__=='__main__':unittest.main()
