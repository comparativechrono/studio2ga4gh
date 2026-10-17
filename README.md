# studio2ga4gh

Convert a [Pedigree Studio](https://github.com/comparativechrono/PedigreeStudio)
drawing into the two GA4GH files that describe a family:

- a **GA4GH Pedigree**, in the Phenopackets form of the published standard:
  every person is a Phenopacket v2, and every relationship a term of KIN, the
  Kinship Ontology;
- a **Phenopackets Family**, written exactly to the Phenopackets v2 schema,
  with the whole family's pedigree and the proband's and relatives' findings.

The files are written by [pedigree-ga4gh](https://github.com/comparativechrono/pedigree-ga4gh),
the one GA4GH implementation that studio2ga4gh, ga4gh2studio, the phenopacket
toolkit and the Pedigree workbench share, and they pass phenopacket-tools'
checks. Its [notes on the GA4GH form](https://github.com/comparativechrono/pedigree-ga4gh/blob/main/docs/ga4gh.md)
explain what is written and why.

## Installation

```bash
pip install studio2ga4gh
```

It needs Python 3.9 or later and installs pedigree-ga4gh with it.

## Usage

```bash
studio2ga4gh okafor.studio.json --terms terms.json
studio2ga4gh okafor.studio.json --terms terms.json -o okafor -d results/
```

For each family in the drawing this writes `okafor_ga4gh-pedigree.json` and
`okafor_phenopackets-family.json` (with `_2`, `_3` … before the ending when the
drawing holds more than one family). The summary lists what was written and
anything that needs attention, such as a condition without an ontology term.

| Option | What it does |
|---|---|
| `-t`, `--terms FILE` | Matches the condition names in the drawing's colour key to ontology terms (see below). |
| `--ids numbers` | Names people by their pedigree numbers, as Pedigree Studio shows them (II-3). The default. |
| `--ids drawing` | Uses the labels shown in the drawing instead, which may be names. |
| `--ids studio` | Uses Pedigree Studio's internal ids. |
| `--only pedigree`, `--only family` | Writes only one of the two files. |
| `--family-id ID` | The family's id (default `FAM1`, `FAM2` …). |
| `--created-by TEXT` | What goes in `metaData.createdBy` (default `studio2ga4gh 0.4.0`). |

### Ontology terms for the conditions

A disease or phenotype is only valid with an ontology id, so each condition in
the colour key needs a term. Give them in a terms file:

```json
{
  "Breast cancer": "MONDO:0007254",
  "Hearing loss from birth": {"id": "HP:0000365", "label": "Hearing impairment"}
}
```

or write the id in the colour key itself: `Breast cancer [MONDO:0007254]`.
Names are matched without regard to case, and the mapping files of hponorm and
mondonorm (`--mapping`) and the decision files of `phenotk normalise` work as
terms files too. An HPO term makes the condition a phenotypic feature and any
other term (Mondo, OMIM, Orphanet) a disease; a `"kind"` of `"disease"` or
`"phenotype"` in the terms file overrides that.

A condition without a term is **left out**, with a note, rather than written
with an empty id. hponorm, mondonorm or the Pedigree workbench's *Match
conditions to terms* will find the terms.

## What the drawing becomes

| In Pedigree Studio | In the GA4GH files |
|---|---|
| square, circle, diamond | sex `MALE`, `FEMALE`, `UNKNOWN_SEX` |
| slash (deceased) | vital status `DECEASED` (otherwise `ALIVE`) |
| arrow (proband) | `indexPatients`, and the Family's proband |
| fill, halves, quarters, shading | a disease or phenotypic feature for each condition named in the colour key |
| child line from a couple | `isBiologicalMotherOf`, `isBiologicalFatherOf` (`isBiologicalParentOf` when the parent's sex is unknown) |
| dashed child line | `isAdoptiveParentOf` |
| D in a parent's symbol | `isSpermDonorOf` or `isOvumDonorOf` |
| S in a parent's symbol | `isGestationalCarrierOf` (not a biological parent) |
| identical or non-identical twins | `isMonozygoticMultipleBirthSiblingOf`, `isPolyzygoticMultipleBirthSiblingOf` |
| consanguineous couple | `isConsanguineousPartnerOf` |
| separated couple | `isSeparatedPartnerOf` |
| couple without children | `isPartnerOf` |
| pregnancy loss (triangle) | a person with vital status `DECEASED`, noted in the narrative |
| "no children" and "infertility" bars | not people: noted in the narrative |
| carrier dot, presymptomatic line, P | noted in the narrative (Phenopackets have no field for them) |

Relationships are written in the standard's reduced form: parents to their
children, partners only when their children don't already say so, twins all
relative to one twin, and no siblings, since shared parents imply them.

Names and other notes written under the symbols are never exported:
Phenopackets have no field for a name, and such notes are often personal data.

## In Python

```python
import json
import studio2ga4gh

with open("okafor.studio.json") as fh:
    drawing = json.load(fh)
with open("terms.json") as fh:
    terms = json.load(fh)

result = studio2ga4gh.convert(drawing, "okafor", terms=terms)
print(result.summary)
for name, text in result.files:      # (file name, JSON text)
    print(name)
```

`convert_file(path, output_prefix=None, output_dir=None, **options)` reads the
drawing and writes the files.

## Changes from 0.3

Version 0.3 wrote its own JSON for the GA4GH Pedigree, which neither form of
the standard uses, and Phenopackets that failed the v2 schema. 0.4 writes
through pedigree-ga4gh instead. Files from 0.3 can be converted with
`pedigree-ga4gh upgrade`. Also new in 0.4:

- the files are named `_ga4gh-pedigree.json` and `_phenopackets-family.json`
  (0.3: `_ga4gh.json` and `_phenopackets.json`);
- people are named by their pedigree numbers unless you ask otherwise;
- conditions without an ontology term are left out, with a note;
- `--phenotypes` is still accepted, but changes nothing: whether a condition
  is a disease or a phenotype now follows its term. `--include-names` is now
  the same as `--ids drawing`.

See [CHANGELOG.md](CHANGELOG.md).

## Licence

MIT
