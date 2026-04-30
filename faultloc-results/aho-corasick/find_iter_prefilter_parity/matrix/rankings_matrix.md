# 6-config rank matrix — `FindIterPrefilterParity`

Single faultloc run (1 trial, 1 RNG seed), with the analysis re-run six times against subsets of the same `coverage/indices.json`. Goal: separate the effect of mutation-loop budget (100 / 500 / 1000 mutations considered) from the effect of including/excluding the initial-sweep positive snapshots.

## Source run composition

- Failing seed found after 26 passes during the outer 0..20000 random sweep, all 26 captured as initial-pass snapshots (indices 1001..1026).
- Mutation loop: 1001 iterations from the failing seed → 432 positives + 568 negatives + 0 discards.
- Total positives available: 458 (432 mutation + 26 initial). Total negatives: 569 (568 mutation + 1 seed).

## Subset configurations

| Config | total_regions | regions with delta>0 | positives | negatives |
| --- | ---: | ---: | ---: | ---: |
| mut=100, init=with | 9296 | 1615 | 71 | 56 |
| mut=100, init=without | 9296 | 863 | 45 | 56 |
| mut=500, init=with | 9296 | 1024 | 240 | 287 |
| mut=500, init=without | 9296 | 807 | 214 | 287 |
| mut=1000, init=with | 9296 | 871 | 458 | 569 |
| mut=1000, init=without | 9296 | 835 | 432 | 569 |

## Rank of `Compiler::build_trie` (best region in the function)

Format `rank / score`. The rank is among regions with `delta > 0` for the human view; `tarantula/ochiai/dstar/jaccard/op2` are SBFL metrics, `delta` is raw `negative_avg − positive_avg`.

| Config | ochiai | tarantula | dstar | jaccard | op2 | delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mut=100, init=with | 226 / 0.75592 | 303 / 0.62831 | 226 / 74.6666 | 256 / 0.57142 | 225 / 55.4166 | 215 / 5.07042 |
| mut=100, init=without | 2 / 0.88191 | 2 / 0.73770 | 2 / 196.0 | 2 / 0.77777 | 2 / 55.6521 | 19 / 4.98492 |
| mut=500, init=with | 2 / 0.85024 | 5 / 0.68571 | 2 / 748.809 | 2 / 0.72292 | 2 / 286.543 | 32 / 3.57935 |
| mut=500, init=without | 2 / 0.87953 | 4 / 0.71812 | 2 / 980.583 | 2 / 0.77358 | 2 / 286.609 | 22 / 4.15155 |
| mut=1000, init=with | 2 / 0.86299 | 4 / 0.70137 | 2 / 1660.31 | 2 / 0.74476 | 2 / 568.575 | 25 / 3.80813 |
| mut=1000, init=without | 2 / 0.87806 | 4 / 0.71880 | 2 / 1915.74 | 2 / 0.77100 | 2 / 568.609 | 22 / 4.10934 |

## Best build_trie region in each config (where the rank above came from)

| Config | Best region (line:col) | ef | ep | nf | np | ochiai |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| mut=100, init=with | `1098:21-1098:39` | 56 | 42 | 0 | 29 | 0.7559 |
| mut=100, init=without | `1098:21-1098:39` | 56 | 16 | 0 | 29 | 0.8819 |
| mut=500, init=with | `1098:21-1098:39` | 287 | 110 | 0 | 130 | 0.8502 |
| mut=500, init=without | `1098:21-1098:39` | 287 | 84 | 0 | 130 | 0.8795 |
| mut=1000, init=with | `1098:21-1098:39` | 569 | 195 | 0 | 263 | 0.8629 |
| mut=1000, init=without | `1098:21-1098:39` | 569 | 169 | 0 | 263 | 0.8780 |

## Why the rank moves the way it does

**Best region across most configs**: `noncontiguous.rs:1098:21-1098:39` — this corresponds to the `continue 'PATTERNS;` statement that triggers the leftmost-first short-circuit. **That is the line whose execution causes the moved-after `prefilter.add(pat)` (lines 1132-1136) to be skipped — i.e. the actual bug-triggering branch.** SBFL is correctly identifying the single line whose execution most strongly correlates with the property failing.

**Including initial-sweep positives slightly degrades SBFL ranks** (rank holds at 2 but score drops by 0.01-0.03). The initial-sweep positives are random pattern sets — most of them still hit `continue 'PATTERNS` at least once, increasing `ep` and shrinking the `ef-ep` gap. The mut=100 row is most affected because the 26 initial positives nearly outnumber the 45 mutation positives there.

**Mutation budget barely matters once it's ≥ 500**: ranks are stable at 2 across mut=500 and mut=1000. The discriminating signal is fully captured by the first ~500 mutations; the next 500 just add proportional noise to both sides.

**Raw delta is consistently rank ~22-32** regardless of config. Delta picks up downstream hot loops first; the initial-pass effect on it is real but inconsistent.

## Comparison to run3 (different RNG seed)

Run3 saw `build_trie` ranked 385+ across all SBFL metrics. The failing seed in that trial had a structure where every build_trie region was hit on every positive AND every negative snapshot (ef=413, ep=604, nf=0, np=0 for all 35 build_trie regions) — zero discriminating signal. The current trial's failing seed is structured such that `continue 'PATTERNS` only fires on 39% of positives but 100% of negatives, giving a ~0.88 Ochiai. **Trial-to-trial variance is dominated by failing-seed structure, not by analysis-config knobs.**

Practical implication: a one-shot faultloc run is a fragile signal. Aggregating across N independent trials (different RNG seeds → different failing seeds → different mutation neighborhoods) would give a stabler ranking. The current crabcheck flow only produces one failing-seed snapshot per invocation — running the binary K times with different seeds and pooling indices would be the smallest change.
