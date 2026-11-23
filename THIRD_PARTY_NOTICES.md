# Third-party notices

This project builds word lists locally from pinned sources. No word list is redistributed
with the source code, and the classic Wordle lists are never bundled (see §"User-supplied
lists" below).

The engine uses **SCOWL** and **ENABLE** for word lists, and **numpy**, **pydantic** and
**typer** at runtime. Phase 5 added **wordfreq** as an optional runtime dependency for the
Zipf prior; Phase 7 added **FastAPI**/**uvicorn** for the optional HTTP adapter and
**httpx** for its tests. **WordNet** and **Open English WordNet** remain unused.

---

## SCOWL 2020.12.07

Source: <https://downloads.sourceforge.net/project/wordlist/SCOWL/2020.12.07/scowl-2020.12.07.zip>
(verified by SHA-256 in `sources.lock`; the licence text ships in the archive as `Copyright`).

> The collective work is Copyright 2000-2018 by Kevin Atkinson as well
> as any of the copyrights mentioned below:
>
>   Copyright 2000-2018 by Kevin Atkinson
>
>   Permission to use, copy, modify, distribute and sell these word
>   lists, the associated scripts, the output created from the scripts,
>   and its documentation for any purpose is hereby granted without fee,
>   provided that the above copyright notice appears in all copies and
>   that both that copyright notice and this permission notice appear in
>   supporting documentation. Kevin Atkinson makes no representations
>   about the suitability of this array for any purpose. It is provided
>   "as is" without express or implied warranty.

The archive's `Copyright` file contains further notices for the component lists
(including 12Dicts, Moby, and UK English lists). Those notices are part of the pinned
source and are not reproduced here; read `data/raw/scowl/Copyright` after fetching the
source.

## ENABLE 2K

Source: <https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt>
(verified by SHA-256 in `sources.lock`).

The ENABLE word list is released into the public domain by its maintainers and
contributors. It is used here as an additional source of valid guesses for the
`extended` and `full` profiles. No copyright notice is attached to the distributed list.

## WordNet 3.0 — not used

Reserved for later phases. If it is ever used, the Princeton licence text must be
reproduced here in full.

## Open English WordNet — not used

Reserved for later phases. If it is ever used, attribution to Princeton WordNet and the
Open English WordNet team under CC BY 4.0 is required.

## wordfreq 3.1.1 — optional runtime dependency

Source: <https://pypi.org/project/wordfreq/>. Data: <https://doi.org/10.5281/zenodo.7199437>
(Speer, R. *wordfreq*). The word-frequency data files are licensed **CC BY-SA 4.0**; the
package code is MIT.

wordfreq is installed only through the `prior` extra and is read at runtime to compute
Zipf scores (`wordle_ai.engine.prior.ZipfPrior`). The scores are cached in process memory
and are **never written to disk or redistributed** by this project, and no derived
frequency table is committed. Calibration output contains aggregate metrics and the
profile's own answer words, not a wordfreq-derived dictionary.

## FastAPI, Starlette, uvicorn — optional HTTP adapter

Installed only through the `http` extra. FastAPI and Starlette are MIT licensed
(<https://github.com/fastapi/fastapi>); uvicorn is BSD-3-Clause
(<https://github.com/encode/uvicorn>). They serve `wordle_ai.api.http`, which contains no
solver logic and no data redistribution.

## httpx — development dependency

BSD-3-Clause (<https://github.com/encode/httpx>). Used by the test suite through
Starlette's `TestClient`; not a runtime dependency of the solver.

## numpy, pydantic, typer

numpy is BSD-3-Clause (<https://numpy.org>); pydantic is MIT
(<https://github.com/pydantic/pydantic>); typer is MIT
(<https://github.com/fastapi/typer>). These are the three required runtime dependencies.

## User-supplied lists (classic Wordle answers and allowed guesses)

The classic answer and allowed-guess lists have **no verified open licence**. They are
never downloaded, bundled, committed or redistributed by this project. They exist only in
`data/user/`, which is excluded by `.gitignore`, and are imported only after the user
passes `--attest-license` to `wordle-ai lex fetch --source user`. Any artifact derived
from them — including `data/processed/classic.en.5/` — carries
`"license": "unverified; never redistributed"` in its manifest and must not be published.
