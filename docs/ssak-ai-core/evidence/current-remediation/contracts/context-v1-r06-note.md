# C01 / R06 schema delta

`ContextPackagePayload` gained:
- `omitted_handle_count: int = 0`
- `omitted_exclusion_count: int = 0`

Reason: bounded handle/exclusion pages must report how many metadata rows were dropped so serialization stays inside request budget without deleting canonical history.
