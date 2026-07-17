# 사실 검토

> 🌐 [English](review.en.md) | **한국어**

## 사실 검토 (`factlog review` / `accept` / `reject`)

추출은 사실을 `candidate` 또는 `needs_review` 로 표시하며, `confirmed`/`accepted`
사실만 엔진 입력이 됩니다. `facts/candidates.csv` 를 직접 손대지 않고 승격하거나
폐기할 수 있습니다.

*터미널에서 실행 (후보를 사람이 검토·승인하는 게이트):*

```bash
factlog review                       # list the pending queue (candidate + needs_review)
factlog review --status needs_review # narrow to one pending status
factlog accept Acme uses FastAPI     # pending → accepted (compiled into accepted.dl)
factlog accept Acme                  # accept every pending fact about a subject ('-' wildcards a position)
factlog reject Acme uses Datadog     # pending → superseded (retired, kept for audit)
factlog accept Acme uses FastAPI --dry-run
```

`accept`/`reject` 는 **대기(pending) 행만** 변경합니다. `confirmed`/`accepted`/
`superseded` 와 일치하는 항목은 보고만 되고 그대로 유지됩니다(대기 상태가 아닌
사실을 폐기하려면 `factlog eject` 를 사용). 둘 다 `accepted.dl` 을 재컴파일합니다.

상태가 아니라 사실의 **값 자체를 교정**하려면 `factlog amend` 를 사용하십시오.

*터미널에서 실행:*

```bash
factlog amend Widget codename Draft --set-object Falcon --set-note "name finalized" --accept
factlog amend Acme uses FastApi --set-object FastAPI    # fix a typo
```

위치 트리플이 사실을 식별하고(정확히 일치), `--set-subject` / `--set-relation` /
`--set-object` / `--set-note` 가 새 값을 줍니다(최소 하나, 또는 `--accept`). amend
는 `candidates.csv` **와** 그 근거가 되는 `runs/*.json` 을 **둘 다** 갱신하므로
편집이 `/factlog sync` 후에도 살아남습니다(사실의 값은 `runs/*.json` 에 있으며,
merge 가 그로부터 `candidates.csv` 를 재구성합니다). `--accept` 는 `accepted` 로
승격까지 합니다. 신뢰도는 편집할 수 없습니다. `--dry-run` 으로 미리 볼 수 있습니다.

> **내구성(durability):** 사람이 한 `accept`(및 `amend --accept`)는 `reject`/
> `superseded` 와 같은 방식으로 재머지 후에도 보존됩니다 — `/factlog sync` 가
> 여러분의 결정을 되돌리지 않습니다.
