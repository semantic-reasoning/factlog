# Open Questions

This file tracks decisions about candidate facts that require human review.

## 중복 개념 후보

Duplicate review:

No duplicate facts detected. `Claude Code,developed_by,Anthropic` and
`Anthropic,develops,Claude Code` express the same relationship in both
directions — the reverse direction row is marked `needs_review` pending
a decision on whether bidirectional facts should be retained.

## 모호한 관계명

Ambiguity review:

- The term "Claude model family" in the `uses` relation is broad; future sources
  should clarify which specific model versions are referenced.

## 출처 부족

Source review:

All confirmed facts link to sections within `sources/example.md`. The source
document is a summary; primary Anthropic documentation should be added when
available.

## 기존 내용과 충돌할 수 있는 항목

Conflict review:

No conflicts detected in the current fact set. The `developed_by` and `develops`
relations are complementary, not conflicting.

## Pending decisions

- `Anthropic,develops,Claude Code` — marked `needs_review`; decide whether to
  keep bidirectional facts or canonicalise to `developed_by` only.
