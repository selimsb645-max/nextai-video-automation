#!/usr/bin/env python3
"""Restore the owner's private release assets with integrity/path checks."""
from pathlib import Path
import os,json,hashlib,tarfile,requests
ROOT=Path(__file__).resolve().parents[1]
def main():
 m=json.loads((ROOT/'docs/assets_manifest.json').read_text())
 token=os.environ.get('GITHUB_ACCESS_TOKEN')
 if not token:raise SystemExit('Authorize GitHub and inject GITHUB_ACCESS_TOKEN securely; never paste it in chat.')
 h={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
 r=requests.get('https://api.github.com/repos/'+m['private_repo']+'/releases/tags/'+m['release_tag'],headers=h,timeout=30);r.raise_for_status()
 a=next((a for a in r.json()['assets'] if a['name']==m['asset_name'] and a['state']=='uploaded'),None)
 if not a:raise SystemExit('Private runtime asset missing; do not begin production.')
 archive=ROOT/m['asset_name']
 def checksum(p):
  d=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(8388608),b''):d.update(b)
  return d.hexdigest()
 if not archive.exists() or checksum(archive)!=m['archive_sha256']:
  tmp=archive.with_suffix(archive.suffix+'.download')
  hh=dict(h);hh['Accept']='application/octet-stream'
  with requests.get(a['url'],headers=hh,stream=True,timeout=(30,120)) as rr:
   rr.raise_for_status()
   with tmp.open('wb') as f:
    for b in rr.iter_content(8388608):f.write(b)
  if checksum(tmp)!=m['archive_sha256']:raise SystemExit('Archive checksum mismatch, nothing extracted.')
  tmp.replace(archive)
 with tarfile.open(archive,'r:gz') as tar:
  members=tar.getmembers();expected={f['path'] for f in m['files']}
  if {f.name for f in members}!=expected:raise SystemExit('Archive manifest membership mismatch.')
  for member in members:
   dest=(ROOT/member.name).resolve()
   if not dest.is_relative_to(ROOT) or not member.isfile() or member.issym() or member.islnk():raise SystemExit('Unsafe archive member rejected.')
   spec=next(x for x in m['files'] if x['path']==member.name)
   if member.size!=spec['bytes']:raise SystemExit('Asset size mismatch.')
   dest.parent.mkdir(parents=True,exist_ok=True)
   with tar.extractfile(member) as src,dest.open('wb') as out:
    import shutil;shutil.copyfileobj(src,out,8388608)
 print('Verified/restored',len(members),'private runtime assets. No workflow started.')
if __name__=='__main__':main()
