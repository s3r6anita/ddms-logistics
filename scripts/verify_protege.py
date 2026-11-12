"""Headless OWL API/HermiT verification using a caller-supplied Protégé distribution."""
import argparse,json,subprocess,zipfile
from pathlib import Path
SOURCE='''
import java.io.File;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.HermiT.Reasoner;
class CheckSiteOntology {
 public static void main(String[] args) throws Exception {
  var m=OWLManager.createOWLOntologyManager();
  var o=m.loadOntologyFromOntologyDocument(new File(args[0]));
  var r=new Reasoner.ReasonerFactory().createReasoner(o);
  var c=m.getOWLDataFactory().getOWLClass(IRI.create("https://example.org/site-dss#NeedsConfirmationSite"));
  var instances=r.getInstances(c,false).getFlattened();
  if(!r.isConsistent() || instances.size()!=1 || o.getClassAssertionAxioms(c).size()!=0) throw new IllegalStateException("Unexpected entailment");
  System.out.println("SITE_RESULT "+instances.iterator().next().getIRI());r.dispose();
 }
}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--protege-home',type=Path,required=True);p.add_argument('--java',default='java');a=p.parse_args()
 root=Path(__file__).resolve().parents[1];work=root/'.runtime/protege';work.mkdir(parents=True,exist_ok=True)
 src=work/'CheckSiteOntology.java';src.write_text(SOURCE)
 hermit=a.protege_home/'plugins/org.semanticweb.hermit-1.4.3.456.jar'
 for jar in [a.protege_home/'bundles/owlapi-osgidistribution.jar',hermit]:
  with zipfile.ZipFile(jar) as z:
   for name in z.namelist():
    if name.endswith('.jar'):(work/Path(name).name).write_bytes(z.read(name))
 cp=':'.join(map(str,[a.protege_home/'bundles/*',hermit,work/'*']))
 r=subprocess.run([a.java,'-Djava.awt.headless=true','-cp',cp,str(src),str(root/'reports/stages1_4/site_dss.owl')],capture_output=True,text=True,check=True)
 line=next(x for x in r.stdout.splitlines() if x.startswith('SITE_RESULT '))
 report=dict(engine='Protégé 5.6.9 OWL API/HermiT, headless',consistent=True,asserted_needs_confirmation=0,inferred_needs_confirmation=1,individual=line[12:],desktop_gui='not exercised')
 (root/'reports/stages1_4/protege_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
