from pathlib import Path
import json,hashlib,subprocess,difflib,tempfile,shutil
r=Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai');b=Path(Path('/tmp/root-startup-evidence-path').read_text().strip())
files=['src/antigravity_k/engine/gbrain.py','src/antigravity_k/engine/global_memory_provider.py','src/antigravity_k/engine/context_shaper.py','tests/test_gbrain_storage_root_contract.py','tests/test_startup_storage_roots_contract.py']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();base=json.loads((b/'baseline.json').read_text());git=lambda *a:subprocess.check_output(['git',*a],cwd=r)
protected={f:sha(r/f) for f in base['source_sha256'] if f not in files};changed={f:{'before':base['source_sha256'][f],'after':s} for f,s in protected.items() if s!=base['source_sha256'][f]}
aliases={}
for f,change in changed.items():
 p=r/f;assert p.is_symlink() and p.resolve() in [r/x for x in files];aliases[f]={**change,'symlink_target':str(p.readlink()),'resolved_target':str(p.resolve()),'samefile':True}
assert len(aliases)==3
index=git('ls-files','--stage','-z');(b/'index-after.bin').write_bytes(index)
def entries(data):return {rec.split(b'\t',1)[1].decode():rec.decode() for rec in data.split(b'\0') if rec}
ib=entries((b/'index-before.bin').read_bytes());ia=entries(index);names=[p.decode() for p in (b/'staged-before.bin').read_bytes().split(b'\0') if p and not p.startswith(b':')];assert len(names)==97 and all(ib[p]==ia[p] for p in names)
owned={f:sha(r/f) for f in files};patch=[]
for f in files:
 p=b/'candidate-source'/f;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(r/f,p);pre=b/'preimage'/f;original=pre.read_text() if pre.exists() else '';patch.append('diff --git a/'+f+' b/'+f+'\n');patch.extend([] if pre.exists() else ['new file mode 100644\n']);patch.extend(difflib.unified_diff(original.splitlines(True),(r/f).read_text().splitlines(True),fromfile='a/'+f if pre.exists() else '/dev/null',tofile='b/'+f))
(b/'root-preimage-only.patch').write_text(''.join(patch))
with tempfile.TemporaryDirectory(prefix='root-storage-reconstruct-') as tmp:
 d=Path(tmp)
 for f in files:
  p=b/'preimage'/f
  if p.exists():t=d/f;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,t)
 argv=['git','apply',str(b/'root-preimage-only.patch')];run=subprocess.run(argv,cwd=d,capture_output=True);assert run.returncode==0;matches={f:sha(d/f)==owned[f] for f in files};assert all(matches.values());(b/'reconstruction.json').write_text(json.dumps({'argv':argv,'returncode':run.returncode,'matches':matches,'basis':'exact ROOT preimages, not clean HEAD modules','stderr':run.stderr.decode()},indent=2))
pre=(b/'preimage'/files[0]).read_text();post=(r/files[0]).read_text();reverse=post.replace('        configured_dir = storage_dir or os.environ.get("AGK_GBRAIN_DIR")\n        self.storage_dir = Path(configured_dir) if configured_dir else Path.home() / ".antigravity" / "gbrain"','        self.storage_dir = Path(storage_dir) if storage_dir else Path.home() / ".antigravity" / "gbrain"',1).replace('            storage_dir: Explicit path, ahead of AGK_GBRAIN_DIR and the default home path.','            storage_dir (str | None): str | None storage dir.',1);assert reverse==pre and 'SharedSystemClient' not in post and 'clear_system_cache' not in post
(b/'lifecycle-preservation.json').write_text(json.dumps({'whole_gbrain_exact_after_reversing_only_approved_ctor_and_doc':True,'root_preimage_sha256':sha(b/'preimage'/files[0]),'root_result_sha256':owned[files[0]],'CHROMA_LIFECYCLE_LOCK_occurrences_before':pre.count('CHROMA_LIFECYCLE_LOCK'),'CHROMA_LIFECYCLE_LOCK_occurrences_after':post.count('CHROMA_LIFECYCLE_LOCK'),'SharedSystemClient_absent':True,'global_cache_clear_absent':True},indent=2))
for n in ['ruff','format','basedpyright','compile']:
 c=json.loads((b/'static-v1'/f'{n}.json').read_text());assert c['returncode']==0 and c['source_sha256']==owned
cases=[]
for suite,count in [('root-gbrain',7),('root-other-stores',12)]:
 inv=json.loads((b/suite/'invocation.json').read_text());assert all(owned[f]==s for f,s in inv['source_sha256'].items());assert json.loads((b/suite/'exit.json').read_text())['returncode']==0;paths=list((b/suite/'captures').iterdir());assert len(paths)==count
 for p in paths:
  data=json.loads((p/'receipt.json').read_text());ci=json.loads((p/'invocation.json').read_text());assert ci['returncode']==0 and data['home_unchanged'];assert data['denied_mutations']==[] and data['socket_attempts']==[] and data.get('model_import_attempts',data.get('embedding_attempts'))==[];assert Path(data['source_path']).is_relative_to(r) and sha(Path(data['source_path']))==data['source_sha256'];cases.append({'suite':suite,'nodeid':ci['nodeid'],'invocation':str((p/'invocation.json').relative_to(b)),'receipt':str((p/'receipt.json').relative_to(b))})
(b/'scenario-evidence.json').write_text(json.dumps(cases,indent=2));(b/'ownership-after.json').write_text(json.dumps({'head_before':base['head'],'head_after':git('rev-parse','HEAD').decode().strip(),'owned_sha256':owned,'independent_protected_python_files':len(protected)-len(aliases),'changed_independent_protected_python':{},'owned_source_symlink_aliases':aliases,'staged97_entries_unchanged':True,'index_entries_before_sha256':base['index_entries_sha256'],'index_entries_after_sha256':hashlib.sha256(index).hexdigest(),'original_staged_paths':names},indent=2));print(json.dumps({'owned_sha256':owned,'patch_sha256':sha(b/'root-preimage-only.patch'),'independent_protected':len(protected)-len(aliases),'staged97':True},indent=2))
