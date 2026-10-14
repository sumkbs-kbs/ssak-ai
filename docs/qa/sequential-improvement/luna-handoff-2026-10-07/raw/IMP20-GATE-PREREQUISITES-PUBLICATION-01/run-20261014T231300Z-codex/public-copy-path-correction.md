# Manifest content-base correction

The first verification stopped before any candidate files were copied. The argv supplement inventory uses paths relative to its parent run while the inventory file itself lives under `argv-revision/`. The copier now records this one content base explicitly; it does not search directories or infer missing artifacts. Existing manifests and source files are preserved.

A second verification also stopped before copying: the registry packet names its public check phase `runtime/`, while disposable state is explicitly under `private-runtime/`. Only that packet's manifest-listed public phase may use the `runtime` component. All private-runtime, cache, auth and private-raw subtrees remain forbidden.
