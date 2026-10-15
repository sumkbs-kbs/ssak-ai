# Evidence script runtime correction

Initial invocation: `python3 record_evidence.py`.

Exit 1 occurred at `zip(linear, (0.2126, 0.7152, 0.0722), strict=True)`:
`TypeError: zip() takes no keyword arguments`.

The shell's system Python predates this supported keyword. The next invocation uses the candidate's existing project virtual environment. No product code or CSS was changed to work around this evidence-only runtime mismatch. The initial script had already written the same task-only patch and postimage before failing to calculate contrast; it had not written a successful result.
