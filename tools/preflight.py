#!/usr/bin/env python3
"""Offline-only checks. Never produces/uploads a video or starts a workflow."""
from pathlib import Path
import ast,json,shutil,subprocess,datetime as dt
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
def main():
 errors=[];warnings=[]
 for p in ROOT.rglob('*.json'):
  if '.git' in p.parts or 'yt-auth' in p.parts:continue
  try:json.loads(p.read_text())
  except Exception:errors.append('Invalid JSON: '+str(p.relative_to(ROOT)))
 for p in list((ROOT/'factory').glob('*.py'))+list((ROOT/'tools').glob('*.py')):
  try:ast.parse(p.read_text())
  except SyntaxError:errors.append('Invalid Python: '+str(p.relative_to(ROOT)))
 for cmd in ['ffmpeg','ffprobe']:
  if not shutil.which(cmd):errors.append(cmd+' missing')
  else:
   r=subprocess.run([cmd,'-version'],capture_output=True,text=True)
   if r.returncode:errors.append(cmd+' not runnable')
 source=ast.parse((ROOT/'factory/factory.py').read_text())
 f=next(x for x in source.body if isinstance(x,ast.FunctionDef) and x.name=='next_bd_slot')
 env={'json':json,'os':__import__('os'),'BASE':str(ROOT/'factory'),'_dt':dt,'ZoneInfo':ZoneInfo}
 exec(compile(ast.Module(body=[f],type_ignores=[]),'offline_slot_test','exec'),env)
 tests=[('long','2026-10-03T09:30:00+06:00','19:30'),('long','2026-10-03T13:30:00+06:00','23:30'),('short','2026-10-03T12:00:00+06:00','22:00'),('short','2026-10-03T16:30:00+06:00','02:30'),('short','2026-10-03T20:30:00+06:00','06:30')]
 for kind,when,want in tests:
  try:
   _,date=env['next_bd_slot'](kind,dt.datetime.fromisoformat(when))
   assert date.strftime('%H:%M')==want
   assert 8<=(date-dt.datetime.fromisoformat(when)).total_seconds()/3600<=10
  except BaseException:errors.append('Schedule sample failed: '+kind+' '+when)
 try:env['next_bd_slot']('long',dt.datetime.fromisoformat('2026-10-03T11:31:00+06:00'));errors.append('Late-window guard failed')
 except SystemExit:pass
 missing=[]
 m=ROOT/'docs/assets_manifest.json'
 if m.exists():
  for item in json.loads(m.read_text())['files']:
   p=ROOT/item['path']
   if not p.exists() or p.stat().st_size!=item['bytes']:missing.append(item['path'])
  if missing:warnings.append(str(len(missing))+' assets not yet restored from private release')
 token=ROOT/'yt-auth/token_nextai.json'
 if not token.exists():warnings.append('YouTube authorization intentionally not included; secure owner setup required')
 else:
  d=json.loads(token.read_text())
  if not all(d.get(x) for x in ['client_id','client_secret','refresh_token']):warnings.append('YouTube authorization incomplete; do not run production')
 print(json.dumps({'mode':'offline_no_upload','syntax_and_schedule_ok':not errors,'errors':errors,'warnings':warnings,'auth_network_checked':False,'clean_install_or_full_render_tested':False},ensure_ascii=False,indent=2))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
