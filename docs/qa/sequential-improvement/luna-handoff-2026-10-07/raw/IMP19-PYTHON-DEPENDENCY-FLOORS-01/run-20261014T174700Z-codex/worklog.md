# Python dependency floor remediation

- Parent candidate: 367863ce56774ea022e6ae75e255dca41f53fc18; historical d868 audit: 24 unresolved records across seven packages. Duplicate advisory records are retained.
- Primary advisories and PyPI releases confirm patched minima: anyio 4.14.2, pyjwt 2.15.0, fsspec 2026.6.0, multidict 6.9.1, oauthlib 4.0.0, sentence-transformers 5.6.0, urllib3 2.8.0.
- OAuthlib metadata differs: the GitHub advisory displays 3.3.2 while the published PYSEC record and actual released changelog identify 4.0.0. Use the released 4.0.0 and verify the real audit. Its changelog removes JSONP revocation support and changes OAuth provider validation order; those provider APIs are not assumed compatible without checking project uses.
- Scope: standard package metadata floors and resolver-generated uv.lock. No audit exception is invented. Retain the existing chromadb version/exception binding unless separately verified and changed.
- Protect shared ROOT staged 97 files; pyproject.toml and uv.lock were observed clean at the start. Source edits happen first in the owned worktree.

References:

- https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6
- https://github.com/jpadilla/pyjwt/security/advisories/GHSA-x33g-cr3x-6449
- https://github.com/fsspec/filesystem_spec/security/advisories/GHSA-27vj-qcqg-25rc
- https://github.com/aio-libs/multidict/security/advisories/GHSA-54p9-h82j-f925
- https://github.com/oauthlib/oauthlib/security/advisories/GHSA-xpv3-w29h-x7cv
- https://raw.githubusercontent.com/oauthlib/oauthlib/v4.0.0/CHANGELOG.rst
- https://pypi.org/project/oauthlib/4.0.0/
- https://github.com/huggingface/sentence-transformers/releases/tag/v5.6.0
- https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw
