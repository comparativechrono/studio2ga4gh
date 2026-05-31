# studio2ga4gh

Convert Pedigree Studio session JSON files to GA4GH interoperability formats:

- **GA4GH Pedigree Standard** — relationship-graph model using the Kinship Ontology (KIN)
- **Phenopackets Family** — PED-compatible pedigree with disease information

## Installation

```bash
pip install studio2ga4gh
```

## Usage

### Command line

```bash
studio2ga4gh session.json
studio2ga4gh session.json -o my_family -d ./output/
```

This produces two files per pedigree:
- `{name}_ga4gh.json` — GA4GH Pedigree (relationship graph with KIN ontology codes)
- `{name}_phenopackets.json` — Phenopackets Family (PED-compatible pedigree + diseases)

### Python API

```python
import studio2ga4gh, json

with open("session.json") as f:
    session = json.load(f)

result = studio2ga4gh.convert(session)
print(result.summary)
for filename, content in result.files:
    print(f"--- {filename} ---")
    print(content[:200])
```

## What Each Output Contains

### GA4GH Pedigree (`_ga4gh.json`)

The rich graph-based format from the GA4GH Pedigree Standard. It represents each parent-child and twin relationship as an explicit edge with a KIN ontology code:

| Relationship | KIN Code | Label |
|-------------|----------|-------|
| Biological mother | KIN:027 | isBiologicalMotherOf |
| Biological father | KIN:028 | isBiologicalFatherOf |
| Adoptive parent | KIN:022 | isAdoptiveParentOf |
| Identical twin | KIN:010 | isMonozygoticMultipleBirthSiblingOf |
| Non-identical twin | KIN:011 | isDizygoticMultipleBirthSiblingOf |

Dashed child lines in Pedigree Studio (adoption) are exported as `isAdoptiveParentOf` rather than biological parent relationships.

### Phenopackets Family (`_phenopackets.json`)

The GA4GH Phenopackets schema `Family` element, containing:
- A PED-compatible `pedigree` with `Person` records (familyId, individualId, parents, sex, affectedStatus)
- A `proband` Phenopacket with disease terms extracted from the legend
- `relatives` Phenopackets for affected family members with their diseases
- `consanguinousParents` flag if any consanguineous partnerships exist

## Phenotype Mapping

Disease/condition names are taken from the Pedigree Studio legend labels. The converter maps visual markers to affected status using the same logic as studio2ped.

## Multiple Pedigrees

If the session contains disconnected pedigrees, numbered file pairs are produced:
```
pedigree_1_ga4gh.json
pedigree_1_phenopackets.json
pedigree_2_ga4gh.json
pedigree_2_phenopackets.json
```

## License

MIT
