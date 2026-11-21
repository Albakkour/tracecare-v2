# Data

TraceCare uses **synthetic** transcripts and two open research datasets. No real patient data.

The raw datasets are not committed (see `.gitignore`). Place them here to rebuild the bundled samples:

| Folder | Dataset | Used for |
|---|---|---|
| `aci-bench-corpus/` | ACI-Bench — 207 role-played doctor–patient conversations with reference notes ([repo](https://github.com/wyim/aci-bench), [paper](https://www.nature.com/articles/s41597-023-02487-3)) | Four encounters bundled as demo samples (with their human-written reference notes for comparison); parser support for the `[doctor]` / `[patient]` format; offline evaluation script |
| `rnpmf-osfstorage-archive/` | PLABA — plain-language adaptations of biomedical abstracts, sentence-aligned ([OSF](https://osf.io/rnpmf/)) | A few sentence pairs used as plain-language *style* references in the Claude patient-explanation prompt |

Rebuild the bundled files (outputs are checked in under `backend/app/`):

```bash
backend/.venv/bin/python -I scripts/build_samples.py data/aci-bench-corpus data/rnpmf-osfstorage-archive
```

Run the offline evaluation over ACI-Bench with the demo provider (no API calls):

```bash
cd backend && .venv/bin/python -I ../scripts/evaluate_aci.py ../data/aci-bench-corpus
```

Check each dataset's license and cite the source papers when presenting results.
