# factlog

> 🌐 [English](README.en.md) | **한국어**

> facts + logic — 마크다운 소스를 **검증 가능하고 출처로 뒷받침되는 사실(fact)**로
> 바꿔 주는 Claude Code 스킬입니다. 추출은 LLM이, 검증은 결정론적 Datalog/wirelog
> 엔진이 맡습니다.

## 개요

factlog는 마크다운 지식베이스(knowledge base)를 정직하게 유지해 주는
[Claude Code](https://code.claude.com) **스킬**입니다. 원칙은 단 하나입니다.

> 에이전트는 결론을 내리지 않는다. 파일을 만들고 CLI를 호출할 뿐이다.
> 검증 가능한 리포트는 CLI가 돌려준다.

- **추출은 LLM(세션 안의 Claude)이 맡습니다** — `sources/`에서 후보 사실을 뽑고,
  자연어 질문을 Datalog 쿼리 초안으로 옮기며, 제한된 범위 안에서 자기 교정을
  시도합니다.
- **검증은 결정론적 엔진([pyrewire](https://github.com/semantic-reasoning/PyreWire)
  기반 wirelog)이 맡습니다** — 확정된 사실을 컴파일하고 로직 체크를 돌려, 정책
  위반·모순·`review_required` 항목을 드러냅니다.

모델이 내놓은 결과는 엔진과 사람이 확인하기 전까지 모두 *후보(candidate)*일
뿐입니다.

## 동작 방식

![factlog 동작 방식: Claude가 제안하고, 엔진이 검증하며, 사람이 확인합니다](docs/how-it-works.svg)

<details>
<summary>텍스트 버전</summary>

```
sources/        →  Claude extracts        →  facts/candidates.csv, pages/, decisions/
candidates       →  human review           →  confirmed facts
confirmed        →  compile (deterministic) →  facts/accepted.dl
questions        →  Claude drafts query     →  facts/query.dl
accepted + query →  wirelog logic check     →  facts/logic_report.txt   ← 검증 가능한 리포트
review_required  →  Claude repairs (gated)  →  decisions/correction_trace.md
```

</details>

## 소스 파일 형식

`/factlog sync`는 `sources/` 아래의 파일을 하나씩 **세션 안에서 텍스트로 읽어**
사실을 추출합니다. 내장 엔진(`merge_candidates.py`)은 파일을 소스 *경로*로만
추적할 뿐 내용은 결코 파싱하지 않습니다 — 그래서 추출 단계에서 텍스트로 읽히는
파일만 적재됩니다. 바이너리 원본(예: `.docx`)이 그 자체만으로는 사실을 만들어
내지 못하는 이유가 여기에 있습니다.

| 형식 | 상태 | 비고 |
|--------|--------|-------|
| `.md`, `.markdown`, `.txt` | **직접 지원** | UTF-8 텍스트를 있는 그대로 읽습니다. 모든 추출 기준이 전제하는 형식입니다. |
| 그 밖의 UTF-8 텍스트 (`.rst`, `.org`, `.csv`, 소스 코드) | 평문 지원 | 별도 파싱 없이 원시 텍스트로 다룹니다. |
| `.docx`, 바이너리 `.pdf`, `.odt`, `.epub`, `.html`, `.rtf` | **자동 변환** | `factlog ingest` 가 pandoc / textutil / pdftotext 로 텍스트로 바꿉니다. |
| `.hwpx` (한컴 OWPML) | **자동 변환** | 내장 추출기로 처리합니다(외부 도구 불필요). zip 안의 `Contents/section*.xml` 텍스트를 읽습니다. |
| `.hwp` (구형 한컴, HWP 5.x) | **자동 변환** | `hwp5html`(pyhwp) → pandoc → markdown 경로로 표까지 보존합니다. `pip install pyhwp` 와 pandoc 이 필요하며, 없으면 안내 메시지와 함께 보고합니다. |
| `.pptx` (PowerPoint) | **자동 변환** | 내장 추출기로 처리합니다(외부 도구 불필요). zip 안의 `ppt/slides/slideN.xml` 에서 슬라이드 텍스트를 순서대로 읽어 슬라이드당 한 블록으로 변환합니다. 발표자 노트는 빠지고, 표 셀은 셀당 한 줄로 펼쳐집니다(행/열 그룹 구조는 보존되지 않음). |
| `.xlsx`, 이미지 | **변환 안 됨** | 내장 변환기가 없어 안내 메시지와 함께 보고합니다. 수동 변환이 필요합니다. |

`factlog ingest` 는 변환한 텍스트를 KB의 **`runs/sources/`** 디렉터리(다른 생성
런 아티팩트와 같은 위치)에 기록하며, 사용자의 원본이 그대로 남아야 하는
**`sources/` 에는 절대 쓰지 않습니다**. 하위 디렉터리의 원본은 그 구조를 그대로
미러링하므로(`sources/sub/report.pdf` → `runs/sources/sub/report.md`), 서로 다른
폴더에 있는 같은 이름의 파일이 충돌하지 않습니다. 원본은 손대지 않으며, 변환본에는
출처(provenance) 헤더(소스, 변환기, 날짜)가 붙습니다. `sources/` 와
`runs/sources/` 는 둘 다 추출이 읽는 유효한 소스 루트입니다.

> **업그레이드 안내:** 하위 디렉터리 미러링은 기존의 평면(flat) 레이아웃보다
> 나중에 도입됐습니다. 그전에 적재된 KB는 중첩 원본을 평면 변환본
> (`runs/sources/report.md`)으로 갖고 있는데, 이제는 짝이 맞지 않아 중첩
> 바이너리가 커버리지나 `factlog sources` 에서 누락으로 다시 나타날 수 있습니다.
> `factlog ingest --scan --force` 를 다시 실행해 변환본을 미러링된 경로로
> 옮기십시오(그러면 남은 평면 변환본은 삭제됩니다). 최상위(비중첩) 소스는
> 영향받지 않습니다.

```bash
factlog ingest report.docx --target ~/wiki   # → ~/wiki/runs/sources/report.md (pandoc)
factlog ingest --scan --target ~/wiki        # auto-convert every binary under sources/
```

### 활성 KB (설정해 둔 KB를 어디서든 대상으로)

`factlog init`/`setup`(또는 `factlog use <kb>`)을 거치면 선택한 KB가 **활성 KB**로
기록됩니다. 그 덕분에 `ingest`/`ask`/`sync` 를 비롯한 도구들이 어느 작업
디렉터리에서든 그 KB를 대상으로 동작하며, `--target`/`--wiki` 를 따로 줄 필요가
없습니다.

```bash
factlog use ~/wiki        # make ~/wiki the active KB (recorded in config)
factlog where             # show the active KB and how it was resolved
factlog sources           # list registered sources (original, conversion, fact count)
factlog status            # KB state: facts by status, vocabulary, conflicts, logic freshness, engine
cd /anywhere && factlog ingest report.pdf   # → ~/wiki/runs/sources/report.txt
factlog eject report.pdf  # inverse of ingest: remove the conversion + retire its facts
factlog ignore drafts/*.md   # exclude sources from sync (re-extraction)
factlog provenance Acme uses FastAPI   # trace a fact to its source(s)
```

### 어휘 살펴보기 (`factlog vocab`)

`ask` 와 `provenance` 에는 정확한 엔티티/관계 이름이 필요합니다. `factlog vocab`
은 이 이름들을 — 엔티티와 관계를 사용 횟수와 함께 — 나열해, 무엇을 질의할 수
있는지 한눈에 보여 줍니다.

```bash
factlog vocab              # entities + relations (engine facts)
factlog vocab --entities   # just entities
factlog vocab --relations  # just relations (tagged [attribute] / [single-valued] / [typed:<type>])
factlog vocab --all        # include non-engine names (candidate/needs_review/superseded)
```

선언된 속성(attribute) 관계의 객체는 엔티티가 아니라 리터럴이므로 엔티티 목록에서
빠집니다(`status` 와 같은 방식의 타이핑).

### 타입 지정 관계 (`policy/typed-relations.md`)

어떤 관계의 리터럴 객체는 단순 매칭이 아니라 **비교**의 대상이 되어야 합니다.
그래야 결정론적 엔진이 그 값을 정렬(ordering)하거나, 임계값(threshold)으로
거르거나, 범위(range)로 질의할 수 있습니다(예: "2030년 이후 출시", "순위 <= 3").
이런 관계는 `policy/typed-relations.md` 에 선언합니다. 객체가 리터럴인 만큼, 해당
관계는 `policy/attribute-relations.md` 에도 함께 선언해야 합니다.

선언은 한 줄에 하나씩 적습니다:

```
- `relation name` : <type> as <ascii_alias>
```

`<ascii_alias>` 는 비교 가능한 값을 담는 엔진 사이드 관계의 이름입니다. 관계
이름이 비ASCII 여도 엔진 식별자로는 적법하게 남도록, 작성자가 직접 고르는 ASCII
식별자(`[A-Za-z_][A-Za-z0-9_]*`)입니다. 공백이 든 관계 이름은 백틱으로 감쌉니다.

타입은 네 가지입니다:

- `date` — `2030.1` / `2030-01-15` → 정렬 가능한 yyyymmdd. **엔진 투영 지원**
  (정렬/임계값/범위).
- `ordinal` — `rank 3` / `3rd` → 정수 순위. **엔진 투영 지원**.
- `amount` — `100억` / `1,000원` → 정수 기본 단위. **엔진 투영 지원**. 단위 표가
  필요하며, 줄 끝에 인라인으로 붙일 수 있습니다: `: amount as <alias> (억=1e8, 만=1e4, 원=1)`
  (값은 양의 정수). 이 절을 생략하면 기본 단위 표를 씁니다.
- `number` — `1,000` / `3.5` → 수치 크기. **엔진 투영 지원**: 정렬 가능한
  int64 로 ×1000 스케일됩니다(소수점 셋째 자리까지). ⚠️ 비교 술어의 임계값은 반드시
  **스케일된 단위**로 적어야 합니다: `version >= 2.0` → `version_num(S, V), V >= 2000`.
  소수 셋째 자리를 넘는 정밀도는 반올림됩니다(ROUND_HALF_UP).

`factlog vocab` 은 선언된 타입 지정 관계에 `[typed:<type>]` 태그를 붙여 보여
줍니다(예: `[attribute, typed:date]`).

### 사실 찾기 (`factlog search`)

정확한 이름이 떠오르지 않을 때는 `factlog search <term>` 을 쓰면, 주어·관계·객체
전체에서 대소문자를 가리지 않는 부분 문자열 매칭으로 일치하는 사실을(상태와 출처
수와 함께) 찾아 줍니다. 정리하면, `vocab` 은 이름을 나열하고, `search` 는 조각으로
사실을 찾고, `provenance` 는 정확한 트리플을 추적합니다.

```bash
factlog search fastapi   # case-insensitive; matches 'FastAPI'
factlog search acme      # partial — every fact mentioning the fragment
```

### 사실의 출처 추적 (`factlog provenance`)

모든 사실은 자신이 추출된 소스를 기록합니다. `factlog provenance`(별칭 `trace`)
는 일치하는 사실의 근거가 되는 행을 모두 나열합니다 — **소스 경로, 상태,
신뢰도, 노트(추출된 발췌문), 그리고 소스 파일이 디스크에 없을 때 붙는 `[stale]`
표시**까지요. (`superseded`/`needs_review` 를 포함한) 모든 상태가 표시되므로,
폐기된 근거도 계속 눈에 남습니다.

```bash
factlog provenance Acme uses FastAPI   # exact triple
factlog provenance Acme uses           # all objects for (subject, relation)
factlog provenance Acme                # all facts about a subject
factlog provenance - uses              # relation only ('-' wildcards a position)
factlog provenance - - FastAPI         # object only
```

위치 인자는 `(subject, relation, object)` 접두사입니다. 리터럴 `-` 는 그 위치를
와일드카드로 처리하며, 생략한 뒤쪽 위치도 와일드카드로 간주합니다(단, 와일드카드가
아닌 항목이 적어도 하나는 있어야 합니다). 공백이 든 항목은 따옴표로 감싸십시오.

`/factlog ask` 역시 검증된 엔진 답변 아래에 근거 소스 경로(`← <source>`)를 함께
나열하므로, 쿼리로 찾은 사실을 그 자리에서 추적할 수 있습니다.

### 사실 검토 (`factlog review` / `accept` / `reject`)

추출 단계는 사실을 `candidate` 나 `needs_review` 로 표시하고, 엔진 입력이 되는
것은 `confirmed`/`accepted` 사실뿐입니다. `facts/candidates.csv` 를 직접 건드리지
않고도 사실을 승격하거나 폐기할 수 있습니다.

```bash
factlog review                       # list the pending queue (candidate + needs_review)
factlog review --status needs_review # narrow to one pending status
factlog accept Acme uses FastAPI     # pending → accepted (compiled into accepted.dl)
factlog accept Acme                  # accept every pending fact about a subject ('-' wildcards a position)
factlog reject Acme uses Datadog     # pending → superseded (retired, kept for audit)
factlog accept Acme uses FastAPI --dry-run
```

`accept`/`reject` 는 **대기(pending) 행만** 바꿉니다. `confirmed`/`accepted`/
`superseded` 에 해당하는 항목은 보고만 되고 그대로 유지됩니다(대기 상태가 아닌
사실을 폐기하려면 `factlog eject` 를 쓰십시오). 두 명령 모두 `accepted.dl` 을
재컴파일합니다.

상태가 아니라 사실의 **값 자체를 바로잡으려면** `factlog amend` 를 쓰십시오.

```bash
factlog amend Widget codename Draft --set-object Falcon --set-note "name finalized" --accept
factlog amend Acme uses FastApi --set-object FastAPI    # fix a typo
```

위치 트리플로 사실을 정확히 식별하고, `--set-subject` / `--set-relation` /
`--set-object` / `--set-note` 로 새 값을 줍니다(이 중 최소 하나, 또는 `--accept`).
amend 는 `candidates.csv` **와** 그 근거가 되는 `runs/*.json` 을 **함께** 갱신하므로
편집이 `/factlog sync` 뒤에도 살아남습니다(사실의 값은 `runs/*.json` 에 있고,
merge 가 거기서 `candidates.csv` 를 다시 만듭니다). `--accept` 를 주면 `accepted`
로 승격까지 합니다. 신뢰도는 편집할 수 없습니다. `--dry-run` 으로 미리 볼 수
있습니다.

> **내구성(durability):** 사람이 한 `accept`(및 `amend --accept`)는 `reject`/
> `superseded` 와 마찬가지로 재머지 뒤에도 보존됩니다 — `/factlog sync` 가
> 여러분의 결정을 되돌리지 않습니다.

### sync에서 소스 제외하기 (`factlog ignore`)

`/factlog sync` 는 실행할 때마다 **모든** 소스를 다시 추출합니다. 초안, 작업 중인
문서, 외부 문서처럼 특정 소스를 그 대상에서 빼고 싶다면, KB별 **sync-ignore
목록**(`policy/sync-ignore.md`)에 추가하십시오. 무시된 소스는 **수정되더라도**
`/factlog sync`, `factlog ingest --scan`, 커버리지 누락 보고에서 건너뜁니다. 이미
머지된 사실은 그대로 남습니다(사실을 실제로 없애려면 `factlog eject` 를 쓰십시오).

```bash
factlog ignore drafts/*.md sources/wip-notes.md   # add pattern(s)
factlog ignore                                     # list patterns + what they match
factlog ignore --remove drafts/*.md               # remove a pattern
```

`policy/sync-ignore.md` 는 한 줄에 글롭(glob)을 하나씩 적습니다(다른 정책 파일과
같은 너그러운 형식이라 `#` 주석, `-` 불릿, 백틱 인용 항목을 지원합니다. `#` 로
시작하는 패턴은 백틱으로 감싸십시오). 패턴은 소스의 전체 ref(`sources/...` /
`runs/sources/...`)나 소스 루트 기준 경로로 매칭됩니다. 글롭 의미는 이렇습니다:
`*` 와 `?` 는 한 경로 세그먼트 안에 머물고(`/` 를 **넘지 않음**), `**` 는
세그먼트를 넘으며, 끝에 붙은 `/` 는 그 하위 트리 전체를 가리킵니다.

| 패턴 | 매칭 대상 |
|---------|---------|
| `drafts/*.md` | `sources/drafts/x.md` — 단 `sources/drafts/sub/x.md` 는 제외 |
| `drafts/**` (또는 `drafts/`) | `sources/drafts/` 아래 전부 |
| `**/*.md` | 깊이에 상관없이 모든 `.md` |

`factlog sources` 는 무시된 소스를 `[ignored]` 로 표시하고, 커버리지는 이를 누락이
아니라 `excluded` 로 보고합니다.

### 소스 제거 (`factlog eject`) — `ingest` 의 역연산

`factlog eject <source>` 는 적재(ingest)를 되돌립니다. `runs/sources/` 변환본을
지우고, 그 소스에서 추출된 행을 `runs/*.json` 에서 빼며, 그 소스를 인용하는 사실을
폐기합니다. 소스는 파일명, 어간(stem), 또는 KB 기준 상대 경로로 지정할 수
있습니다 — 바이너리 원본(예: `report.pdf`)을 지정하면 그 `runs/sources/<stem>`
변환본까지 함께 매칭되고, 어간만 주면 같은 어간을 쓰는 소스가 모두 매칭됩니다.

```bash
factlog eject report.pdf                 # delete conversion; mark citing facts superseded (kept for audit)
factlog eject report.pdf --purge         # delete the citing candidate rows instead of superseding them
factlog eject report.pdf --delete-original  # also delete the user's original under sources/
factlog eject report.pdf --dry-run       # show the planned changes, modify nothing
```

#### 사실 하나만 제거 (`--fact`)

소스 자체는 멀쩡한데 추출된 사실 하나만 잘못됐다면, 그 사실만 폐기할 수
있습니다 — 소스의 변환본도 원본도 그대로 남습니다.

```bash
factlog eject --fact "을서비스" "정식_운영" "2030.1"      # retire one fact (mark superseded)
factlog eject --fact "갑봇" "통합" "을서비스" --fact "값가" "대체" "값나"   # several at once
factlog eject --fact "을서비스" "정식_운영" "2030.1" --purge   # delete the candidate row instead
```

사실은 **모든** 소스에 걸쳐 그 `(subject, relation, object)` 트리플로 매칭됩니다.
기본값 `superseded` 는 `runs/*.json` 을 건드리지 않아 폐기에 내구성이 있습니다 —
이후 `/factlog sync` 가 소스에서 사실을 다시 주장하더라도 `merge_candidates` 가
그것을 계속 superseded 로 묶어 둡니다. 반면 `--purge` 는 행을 삭제하고
`runs/*.json` 에서도 지웁니다. 소스가 여전히 그 사실을 주장한다면 재싱크 때 다시
추출되므로, 사실을 영구히 폐기하려면 기본값을 쓰십시오. fact 모드와 source 모드는
함께 쓸 수 없고, `--delete-original` 도 `--fact` 와 같이 쓸 수 없습니다.

기본적으로 폐기된 사실은 `superseded` 로 표시되어(감사 목적으로
`facts/candidates.csv` 에 남습니다) `sources/` 아래 원본은 **유지**됩니다 — 그래서
다음 `/factlog sync` 때 다시 변환됩니다. 원본까지 없애려면 `--delete-original` 을
주십시오. `accepted.dl` 은 재컴파일되어, 폐기된 사실이 엔진 입력에서 곧바로
빠집니다.

`runs/sources/` 변환본은 적재 출처 헤더로 그것을 만든 원본과 묶여 있어, 두 원본이
어간을 공유하더라도 `eject report.docx` 가 `report.pptx` 의 변환본을 건드리지
않습니다. `pages/` 는 `eject` 로 다시 만들어지지 않으므로 `/factlog sync` 를
실행해 맞추십시오. 기본값 `superseded` 는 현재 상태를 기준으로 한 폐기입니다.
**텍스트** 원본을 `sources/` 아래 그대로 두면 다음 `/factlog sync` 가 그 사실을
다시 추출·주장하므로, 소스를 영구히 없애려면 `--purge` 나 `--delete-original`
(또는 둘 다)을 주십시오.

해석 우선순위는 이렇습니다: `--target`/`--wiki` 플래그 > `$FACTLOG_ROOT` > 활성 KB
설정(`${XDG_CONFIG_HOME:-~/.config}/factlog/config.json`) > 현재 디렉터리. 설정이
없으면 동작은 종전과 같습니다(현재 디렉터리 사용).

`/factlog sync` 는 첫 단계로 `factlog ingest --scan` 을 실행하므로, `sources/` 에
넣어 둔 바이너리는 자동으로 변환됩니다(멱등적이라 바뀌지 않은 파일은 건너뜁니다).
바이너리에 `runs/sources/` 변환본이 없으면 `merge_candidates.py` 가 경고를 띄워,
조용한 비적재(non-ingestion)를 드러냅니다.

## 요구 사항

- Python **3.11+** (엔진 의존성 `pyrewire` 가 요구)
- **pyrewire 1.0.1+** (`pip install -r requirements.txt`)
- Claude Code CLI

## 설치

factlog는 **Claude Code 플러그인**입니다. Claude Code 세션에서 이 저장소의
마켓플레이스를 통해 설치합니다.

```
/plugin marketplace add semantic-reasoning/factlog
/plugin install factlog@semantic-reasoning
/factlog setup                     # one-shot: deps + doctor + init, in-session
```

`setup` 은 `doctor` 실행, 엔진 의존성(`pyrewire`) 설치, KB 스캐폴딩, 환경 재점검을
한 명령으로 처리합니다.

### 로컬 설치 (개발용)

로컬 클론을 대상으로 개발하려면, 작업 트리 자체를 마켓플레이스로 등록하십시오.

```
/plugin marketplace add ~/git/semantic-reasoning/factlog
/plugin install factlog@semantic-reasoning
```

### `/factlog setup` 이 하는 일

`setup` 은 예전에 따로 나뉘어 있던 설치 후 단계들을 한 명령으로 묶습니다. 손으로
하면 다음과 같습니다.

```bash
pip install -r ~/git/semantic-reasoning/factlog/requirements.txt   # pyrewire>=1.0.1,<2.0
python3 -m factlog doctor          # checks Python 3.11+ and pyrewire
python3 -m factlog init --target ~/wiki   # scaffold the KB layout
```

여러분의 Python이 외부 관리(PEP 668) 상태라면 pip이 그 안으로의 설치를
거부합니다. 이때 `setup` 은 설치를 밀어붙이는 대신 venv 안내를 출력합니다. venv를
만들어 활성화한 뒤 `setup` 을 다시 실행하십시오.

```bash
python3 -m venv ~/.factlog-venv && source ~/.factlog-venv/bin/activate
python3 -m factlog setup --target ~/wiki
```

## 사용법

지식베이스 안의 Claude Code 세션에서(플러그인은 모든 세션에서 활성):

```
/factlog sync      # read sources/, extract candidate facts, update pages & decisions
/factlog query     # translate policy/questions.md into facts/query.dl (Datalog query draft)
/factlog check     # compile accepted facts, run the logic check over accepted + query, show the report
/factlog repair    # attempt gated self-correction of review_required queries
/factlog ask       # answer one question: deterministically routed to the engine (verified) or wiki exploration (unverified)
```

`/factlog check` 에 앞서 `/factlog query` 를 실행하십시오. 로직 체크는
`facts/query.dl` 의 쿼리 초안을 평가하는데, 이 초안은 `/factlog query` 가
`policy/questions.md` 의 자연어 질문에서 생성합니다.

## 결정론과 한계

스킬은 결국 프롬프트이므로, 모델은 각 단계를 실행하도록 *유도*될 뿐 *강제*되지는
않습니다. 그래서 factlog는 신뢰성이 필수인 단계 — 사실 컴파일, wirelog 로직 체크,
정책 컴파일, 검증 — 를 모델의 판단이 아니라 **스킬이 실행하고 신뢰하도록 지시받는
번들 스크립트**에 맡깁니다. 로직 체크 리포트는 언제나 엔진이 생성하며, 모델이
서술하는 것이 아닙니다.

### AC4 — 오래된 편집 방지 (두 단계)

factlog는 서로 다른 두 메커니즘으로 신선도(freshness)를 강제합니다.

| 단계 | 메커니즘 | 보장하는 것 |
|-------|-----------|-------------------|
| **훅으로 강제** | `facts/logic_report.txt` 가 없거나 대상 파일보다 오래됐을 때, `PreToolUse` 훅이 `facts/accepted.dl` 또는 `facts/query.dl` 로의 모든 `Write`/`Edit` 를 거부합니다(`/factlog check` → `run_logic_check.py` 로 갱신) | 로직 리포트가 오래된 상태에서는 엔진의 컴파일된 입력을 덮어쓸 수 없습니다 — 훅이 파일에 닿기 전에 도구 호출을 막습니다 |
| **SKILL 규율 (최선 노력)** | `SKILL.md` 는 어떤 결론을 말하기 전에 Claude가 `run_logic_check.py` 를 실행하고 `facts/logic_report.txt` 를 있는 그대로 보여 주도록 지시합니다 | 모델은 엔진 리포트를 드러내도록 *유도*될 뿐 *강제*될 수는 없습니다(R10: "완전히 보장할 수 없음") — 원시 리포트에 대한 사람의 검토가 최종 검증 단계입니다 |

두 단계는 서로를 보완합니다. 훅은 결정론적 빈틈을 메우고, SKILL 규율은 공학적으로
강제할 수 없는 서술(narration) 계층을 떠맡습니다.

## 라이선스

Apache-2.0 — [LICENSE](LICENSE) 와 [NOTICE](NOTICE) 를 참조하십시오.
