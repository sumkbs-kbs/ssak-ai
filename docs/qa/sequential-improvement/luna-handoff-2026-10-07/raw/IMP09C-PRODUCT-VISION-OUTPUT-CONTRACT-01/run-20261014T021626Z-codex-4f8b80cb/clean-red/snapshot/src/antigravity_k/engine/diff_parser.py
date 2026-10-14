from .diff_models import FilePatch, Hunk


def parse_apply_patch(text: str) -> list[FilePatch]:
    patches: list[FilePatch] = []
    current: FilePatch | None = None
    current_hunk: Hunk | None = None
    lines = text.splitlines()

    for line in lines:
        if line.startswith("*** Begin Patch"):
            continue
        if line.startswith("*** End Patch"):
            if current_hunk and current:
                current.hunks.append(current_hunk)
                current_hunk = None
            if current:
                patches.append(current)
                current = None
            continue
        if line.startswith("*** Add File: "):
            if current_hunk and current:
                current.hunks.append(current_hunk)
                current_hunk = None
            if current:
                patches.append(current)
            path = line[len("*** Add File: ") :].strip()
            current = FilePatch(file_path=path, is_new_file=True)
            continue
        if line.startswith("*** Delete File: "):
            if current_hunk and current:
                current.hunks.append(current_hunk)
                current_hunk = None
            if current:
                patches.append(current)
            path = line[len("*** Delete File: ") :].strip()
            current = FilePatch(file_path=path, is_delete_file=True)
            patches.append(current)
            current = None
            continue
        if line.startswith("*** Update File: "):
            if current_hunk and current:
                current.hunks.append(current_hunk)
                current_hunk = None
            if current:
                patches.append(current)
            path = line[len("*** Update File: ") :].strip()
            current = FilePatch(file_path=path)
            continue
        if line.startswith("*** End File"):
            if current_hunk and current:
                current.hunks.append(current_hunk)
                current_hunk = None
            if current:
                patches.append(current)
                current = None
            continue

        if current and current.is_new_file:
            if line.startswith("+"):
                current.new_file_content.append(line[1:])
            elif line == "":
                current.new_file_content.append("")
            continue

        if current is None:
            continue

        if line.startswith("@@"):
            if current_hunk:
                current.hunks.append(current_hunk)
            ctx_after_marker = line[2:].strip()
            current_hunk = Hunk(context_before=[ctx_after_marker]) if ctx_after_marker else Hunk()
        elif current_hunk is not None:
            if line.startswith("-"):
                current_hunk.removals.append(line[1:])
            elif line.startswith("+"):
                current_hunk.additions.append(line[1:])
            elif line.startswith(" "):
                ctx_line = line[1:]
                if not current_hunk.removals and not current_hunk.additions:
                    current_hunk.context_before.append(ctx_line)
                else:
                    current_hunk.context_after.append(ctx_line)
            elif line == "":
                if not current_hunk.removals and not current_hunk.additions:
                    current_hunk.context_before.append("")
                else:
                    current_hunk.context_after.append("")

    if current_hunk and current:
        current.hunks.append(current_hunk)
    if current:
        patches.append(current)

    return patches
