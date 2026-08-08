# Archived benchmark audit — not the current release

This point-in-time validation design is retained only for protocol provenance.
It is not a supported benchmark, final result source, or alternative PGRR
version. See [`README.md`](README.md) for the current documentation index.

# Moderate v4 benchmark

Moderate v4 is a predeclared, split-safe revision of the moderate social-navigation
benchmark. It retains all v3 geometry, actor dynamics, density levels, and seven of
the eight scenario families unchanged. Its only distributional change is the
`head_on_corridor` interaction.

For each v4 head-on condition, the seed deterministically selects one side of the
corridor. All 1, 2, or 4 pedestrians then follow parallel, non-cyclic, one-shot
routes on that same lane at a configured 0.75 m centerline offset. Starts retain a
1.50 m longitudinal stagger. The opposite 0.75 m lane is checked against the
footprint-inflated static map and remains an explicit recovery channel.

The seed blocks are 72000 (train), 73000 (validation), and 83000 (test), with
3/3/5 repetitions. They are disjoint from one another and from v1--v3. Scenario
IDs, seeds, serialized SHA-256 values, and static A* reachability are validated by
the compiler tests. Results obtained on v4 must be identified as v4 and must not
be pooled with earlier benchmark revisions without reporting the revision change.
