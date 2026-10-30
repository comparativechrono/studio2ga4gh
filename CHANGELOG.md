# Changelog

## 0.4.1

For the symbols of the 2025 correction to the pedigree nomenclature
(Steinhaus French, Bennett and Resta, *J Genet Couns* 2025;34(2):e2020),
which Pedigree Studio now draws:

- G in a parent's symbol is a gestational carrier (`isGestationalCarrierOf`),
  not a biological parent, as S has been. S, which older drawings use, still
  means the same.
- Twins of unknown zygosity (the Studio's "Not known (?)") are
  `isMultipleBirthSiblingOf`, which says nothing about zygosity. 0.4.0 wrote
  every twin that was not identical as `isPolyzygoticMultipleBirthSiblingOf`,
  so it would have called them non-identical.
- Twins joined only through a third get the zygosity that the chain of twin
  lines between them gives: an identical twin shares the other's relation,
  a line of unknown zygosity leaves it unknown, and non-identical twins of a
  non-identical twin stay non-identical. 0.4.0 called them identical only if
  every line in the set was identical, so identical twins joined through a
  third could come out non-identical when another twin in the set was not.
- A consultand (an arrow without a P) is noted in the narrative, as carriers
  and pregnancies are: the GA4GH files have no place of their own for one.

## 0.4.0

studio2ga4gh now writes its files through
[pedigree-ga4gh](https://github.com/comparativechrono/pedigree-ga4gh), the one
GA4GH implementation shared by the lab's pedigree tools, and depends on it.

- The GA4GH Pedigree is written in the Phenopackets form of the published
  standard: every person is a Phenopacket v2, and relationships are
  `{individualId, relation, relativeId}` with current KIN terms, in the
  standard's reduced form. Version 0.3 wrote the conceptual model straight out
  as JSON, which neither form of the standard uses.
- The Phenopackets Family meets the Phenopackets v2 schema: every Phenopacket
  has `metaData`, with `phenopacketSchemaVersion` and a resource, with its
  release, for each ontology used.
- Conditions are matched to ontology terms with `--terms FILE`, or an id in the
  colour key (`Breast cancer [MONDO:0007254]`) of an ontology pedigree-ga4gh
  can declare; anything else in brackets, such as `Hypertension (BP:160/95)`,
  is part of the name. A condition without a term is left out with a note,
  instead of being written with an empty id.
- People are named by their pedigree numbers (II-3) by default; `--ids drawing`
  and `--ids studio` choose the drawing's labels or the Studio's ids, made
  into ids as studio2ped makes them (`J. Mensah` becomes `J_Mensah`). An id
  that would be empty, `0` or shared falls back to the pedigree number, with a
  note. The text under the symbols is never written; with `--ids drawing` the
  drawing's labels, which may be names, are the ids.
- Twins are `isMonozygoticMultipleBirthSiblingOf` or
  `isPolyzygoticMultipleBirthSiblingOf`, as KIN labels them (0.3 used a label
  that KIN does not have), and donors, surrogates, separated and
  consanguineous couples have their own KIN terms.
- "No children" and "infertility" symbols are no longer written as people;
  they, carriers, pregnancies and pregnancy losses are noted in the narrative.
- The files are named `<name>_ga4gh-pedigree.json` and
  `<name>_phenopackets-family.json` (0.3: `_ga4gh.json` and `_phenopackets.json`),
  and `--only`, `--family-id` and `--created-by` are new.
- `--phenotypes` and `--include-names` are kept so that 0.3's commands still
  run: the first changes nothing, and the second is now the same as
  `--ids drawing`, whose ids are the drawing's labels and so may be names.
- `-d` makes the output folder if it does not exist (0.3 reported a missing
  folder as a missing input), and a terms file that is missing or is not JSON
  is reported as such rather than with a traceback.
- `studio2ga4gh_standalone.py` is removed: it was version 0.1.0, wrote the
  old, incorrect form, and could not work without pedigree-ga4gh.
- `__version__` now matches the release (0.3.0 reported 0.1.0), and there are
  tests, run on Python 3.9 to 3.14.

Files written by 0.3 can be converted with `pedigree-ga4gh upgrade`.

## 0.3.0

Released on PyPI on 1 June 2026.
