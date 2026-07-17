# 활성 KB

> 🌐 [English](active-kb.en.md) | **한국어**

## 활성 KB (설정해 둔 KB를 어디서든 대상으로)

`factlog init`/`setup`(또는 `factlog use <kb>`) 이후, 선택한 KB가 **활성 KB**로
기록됩니다. 그래서 `ingest`/`ask`/`sync` 및 도구들이 어느 작업 디렉터리에서든
그 KB를 대상으로 동작합니다 — `--target`/`--wiki` 가 필요 없습니다.

*터미널에서 실행:*

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

> **슬래시 명령(`/factlog …`)도 활성 KB에서 동작합니다.** 다만 factlog **소스
> 저장소 안에서** 실행하면 번들 `examples/sample-kb` 와 혼동될 수 있으니, KB
> 폴더에서 열거나 `factlog use <kb>` 로 활성 KB를 먼저 지정하세요. `factlog where`
> 로 어느 KB가 대상인지 확인할 수 있습니다. 신선도 게이트(PreToolUse 훅)도
> **활성 KB**(`FACTLOG_ROOT > config > cwd` 로 해석된)를 보호합니다 — 활성 KB가
> 아닌 다른 KB의 엔진 입력을 직접 편집하는 경우는 게이트의 대상이 아닙니다.

해석 우선순위: `--target`/`--wiki` 플래그 > `$FACTLOG_ROOT` > 활성 KB 설정
(`${XDG_CONFIG_HOME:-~/.config}/factlog/config.json`) > 현재 디렉터리. 설정이 없으면
동작은 종전과 같습니다(현재 디렉터리 사용).
