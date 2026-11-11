# Minskytron: the original

- `dpys5.original.mac`: Peter Samson's `dpys5.mac` (PDP-1 display hacks, 051209–080415, from the Computer History Museum's PDP-1 restoration), as downloaded from `https://bitsavers.org/bits/DEC/pdp1/from_peter_samson/dpys5.mac` (via the mirror `bitsavers.mirrorservice.org`). The bytes are untouched, with CR line endings. sha256 `d10a796dde8646bcddba92016e40eac2b19aff91594267b352e457987b1835a7`.
- `dpys5.mac`: the same text with CR turned into LF, which `macro1` reads.
- `minskytron.mac`: Minskytron alone, lines 257–364 of `dpys5.mac` verbatim (from `/ start at 500` to `sh5`), with a title and `start 500`.

`build/macro1 -r minskytron.mac` gives 99 words at 500–642, each equal to the word `dpys5.mac` assembles at the same address, and `minskytron.rim` with sha256 `3181d84bb8f363bd166398fc18f2ccefb82c8bce36d06a636314673dc2fbcc62`. That image is the target: the RUNS text in `../runs`, compiled by `tools/runsc.py` with the declarations in `../pdp1`, rebuilds it.
