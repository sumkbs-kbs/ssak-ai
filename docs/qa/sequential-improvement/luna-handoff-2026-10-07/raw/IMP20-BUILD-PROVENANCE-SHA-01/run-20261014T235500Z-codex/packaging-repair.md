# Patch inventory correction

The initial `git diff` captured tracked bundle removals and index changes but omitted the new untracked assets. The replay inventory equality assertion correctly failed before any successful package claim. The incomplete patch is preserved as `task-only-incomplete.patch`.

The final patch is generated in an owned temporary Git repository: commit the exact preimage, overlay all final owned bundle/pin paths, stage additions/removals and emit the complete binary patch. Reset only that disposable replay repository, apply the complete patch and compare the entire final file set and bytes. The candidate repository is never reset by this helper. Successful product/unit/build checks are not repeated for this packaging repair.
