# Known security issues

## DoS/OOM risk

(Including the risk of an accidental self-inflicted DoS "attack")

This package offers open-ended expansion of recurring events and tasks, potentially returning an infinite amount of recurrences.  Those recurrences are returned as a generator, so things will not break down immediately.  However, there is no guaranteed sort order of the recurrences ... and once you add sorting parameters to a search generating infinite expansion, things will blow up.

Even when closed date ranges are utilized, there is no guarantee that the number of recurrences will be manageable.

Some workarounds reducing the risks will probably be considered in a future release.
