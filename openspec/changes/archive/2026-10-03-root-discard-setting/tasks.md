# Tasks

- [x] Add the setting and the tasks, untouched when undefined
- [x] Refuse `false` without an enabled `fstrim.timer`
- [x] Check the options rewrite against real fstab lines
- [x] Update the wiki, changelog and collection version
- [x] Two independent reviews before push

## Verification

- molecule `common` verify drives the tasks against planted fstab copies: the image's line kept
  under `true`, only `discard` removed under `false`, a second `false` unchanged, a sole
  `discard` option becoming `defaults`. Remounting the root is not covered: a container's / is
  an overlay. Run in CI; locally the container's clock was behind and apt refused the mirrors
- Codex adversarial review: accepted the empty options field and the discard variants (the
  rewrite now refuses anything but ext4)
- Claude review: accepted the parse check on a clean fstab (it failed exactly when all was
  fine — now a non-zero parse-error count, checked before the file is replaced), the
  overridable fixture path, the false wiki claim, the timer states; declined collapsing the
  rewrite into a single `replace`, which cannot hold the shape check
