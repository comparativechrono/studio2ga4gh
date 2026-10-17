"""
studio2ga4gh - Convert Pedigree Studio sessions to GA4GH Pedigree and Phenopackets.

Produces two interoperability formats:
1. GA4GH Pedigree (relationship-graph model with KIN ontology codes)
2. Phenopackets Family (PED-compatible pedigree + disease information)
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

__version__ = "0.1.0"

# ── KIN Ontology codes ───────────────────────────────────────────────────
KIN_BIOLOGICAL_MOTHER_OF = {"id": "KIN:027", "label": "isBiologicalMotherOf"}
KIN_BIOLOGICAL_FATHER_OF = {"id": "KIN:028", "label": "isBiologicalFatherOf"}
KIN_ADOPTIVE_PARENT_OF = {"id": "KIN:022", "label": "isAdoptiveParentOf"}
KIN_MONOZYGOTIC_TWIN = {"id": "KIN:010", "label": "isMonozygoticMultipleBirthSiblingOf"}
KIN_DIZYGOTIC_TWIN = {"id": "KIN:011", "label": "isDizygoticMultipleBirthSiblingOf"}

# ── Sex mappings ──────────────────────────────────────────────────────────
SHAPE_TO_SEX_CODE = {
    "male": 1, "female": 2, "unknown": 0,
    "adopted-male": 1, "adopted-female": 2, "adopted-unknown": 0,
    "miscarriage": 0, "no-offspring": 0, "infertile": 0,
}
SEX_CODE_TO_GA4GH = {1: "MALE", 2: "FEMALE", 0: "UNKNOWN_SEX"}
SEX_CODE_TO_PHENOPACKET = {1: "MALE", 2: "FEMALE", 0: "UNKNOWN_SEX"}

# ── Phenopacket affected status ──────────────────────────────────────────
AFFECTED_STATUS = {"MISSING": "MISSING", "UNAFFECTED": "UNAFFECTED", "AFFECTED": "AFFECTED"}


# ── Session data models ──────────────────────────────────────────────────

@dataclass
class Person:
    id: str
    shape: str
    sex: int
    text: str
    fill_mode: str
    fill_color: Optional[str]
    halves: list
    quarters: list
    shading_pattern: str
    shading_coverage: str
    center_text: str
    deceased: bool
    proband: bool
    custom_label: str
    father_id: Optional[str] = None
    mother_id: Optional[str] = None
    family_id: Optional[str] = None
    is_adopted: bool = False  # derived from dashed child link


@dataclass
class Partnership:
    id: str
    from_id: str
    to_id: str
    type: str


@dataclass
class ChildLink:
    id: str
    partnership_id: str
    child_id: str
    dashed: bool


@dataclass
class TwinLink:
    id: str
    child1_id: str
    child2_id: str
    type: str  # 'identical' or 'non-identical'
    partnership_id: str


@dataclass
class Phenotype:
    name: str
    key: str
    is_shading: bool
    color: Optional[str]
    pattern: Optional[str]
    coverage: Optional[str]


@dataclass
class Family:
    family_id: str
    person_ids: set
    persons: dict
    partnerships: list
    child_links: list
    twin_links: list


# ── Session parser ────────────────────────────────────────────────────────

def parse_session(data: dict) -> tuple:
    """Parse Pedigree Studio session JSON. Returns (persons, partnerships, child_links, twin_links, legend_labels)."""
    persons = {}
    for pd in data.get("persons", []):
        pid = pd["id"]
        persons[pid] = Person(
            id=pid, shape=pd.get("shape", "unknown"),
            sex=SHAPE_TO_SEX_CODE.get(pd.get("shape", "unknown"), 0),
            text=pd.get("text", ""),
            fill_mode=pd.get("fillMode", "none"),
            fill_color=pd.get("fillColor"),
            halves=pd.get("halves", [None, None]),
            quarters=pd.get("quarters", [None, None, None, None]),
            shading_pattern=pd.get("shadingPattern", "stripes"),
            shading_coverage=pd.get("shadingCoverage", "full"),
            center_text=pd.get("centerText", ""),
            deceased=pd.get("deceased", False),
            proband=pd.get("proband", False),
            custom_label=pd.get("customLabel", ""),
        )

    partnerships = [Partnership(id=p["id"], from_id=p["fromId"], to_id=p["toId"],
                    type=p.get("type", "normal")) for p in data.get("partnerships", [])]

    child_links = [ChildLink(id=c["id"], partnership_id=c["partnershipId"],
                   child_id=c["childId"], dashed=c.get("dashed", False))
                   for c in data.get("childLinks", [])]

    twin_links = [TwinLink(id=t["id"], child1_id=t["child1Id"], child2_id=t["child2Id"],
                  type=t.get("type", "identical"), partnership_id=t.get("partnershipId", ""))
                  for t in data.get("twinLinks", [])]

    legend_labels = data.get("legendLabels", {})
    return persons, partnerships, child_links, twin_links, legend_labels


# ── Graph analysis (reused from studio2ped) ───────────────────────────────

def detect_families(persons, partnerships, child_links, twin_links):
    adj = defaultdict(set)
    pship_map = {p.id: p for p in partnerships}

    for p in partnerships:
        if p.from_id in persons and p.to_id in persons:
            adj[p.from_id].add(p.to_id)
            adj[p.to_id].add(p.from_id)

    for cl in child_links:
        pship = pship_map.get(cl.partnership_id)
        if pship and cl.child_id in persons:
            for pid in (pship.from_id, pship.to_id):
                if pid in persons:
                    adj[cl.child_id].add(pid)
                    adj[pid].add(cl.child_id)

    for tl in twin_links:
        if tl.child1_id in persons and tl.child2_id in persons:
            adj[tl.child1_id].add(tl.child2_id)
            adj[tl.child2_id].add(tl.child1_id)

    visited = set()
    families = []
    fam_counter = 0

    for pid in persons:
        if pid in visited:
            continue
        fam_counter += 1
        component = set()
        queue = [pid]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            for n in adj.get(current, set()):
                if n not in visited:
                    queue.append(n)

        fam_partnerships = [p for p in partnerships if p.from_id in component or p.to_id in component]
        fam_child_links = [cl for cl in child_links if cl.child_id in component]
        fam_twin_links = [tl for tl in twin_links
                         if tl.child1_id in component or tl.child2_id in component]
        fam_persons = {pid: persons[pid] for pid in component}

        families.append(Family(
            family_id=f"FAM{fam_counter}", person_ids=component,
            persons=fam_persons, partnerships=fam_partnerships,
            child_links=fam_child_links, twin_links=fam_twin_links,
        ))
    return families


def resolve_parents(family):
    pship_map = {p.id: p for p in family.partnerships}
    for cl in family.child_links:
        pship = pship_map.get(cl.partnership_id)
        if not pship:
            continue
        child = family.persons.get(cl.child_id)
        if not child:
            continue
        p1 = family.persons.get(pship.from_id)
        p2 = family.persons.get(pship.to_id)
        if not p1 or not p2:
            continue
        if p1.sex == 1 and p2.sex == 2:
            child.father_id, child.mother_id = p1.id, p2.id
        elif p1.sex == 2 and p2.sex == 1:
            child.father_id, child.mother_id = p2.id, p1.id
        else:
            child.father_id, child.mother_id = pship.from_id, pship.to_id
        if cl.dashed:
            child.is_adopted = True
    for p in family.persons.values():
        p.family_id = family.family_id


# ── ID and phenotype helpers ──────────────────────────────────────────────

def make_individual_id(person):
    if person.custom_label and person.custom_label.strip() and person.custom_label.strip() != "Lbl":
        raw = person.custom_label.strip()
    elif person.text and person.text.strip():
        raw = person.text.strip().split("\n")[0].strip()
    else:
        raw = person.id
    sanitised = re.sub(r"\s+", "_", raw)
    sanitised = re.sub(r"[^\w\-]", "", sanitised)
    return sanitised or person.id


def extract_phenotypes(legend_labels):
    phenotypes = []
    for key, label in legend_labels.items():
        if not label or not label.strip():
            continue
        label = label.strip()
        if key.startswith("shading:"):
            parts = key.split(":")
            phenotypes.append(Phenotype(name=label, key=key, is_shading=True,
                color=None, pattern=parts[1] if len(parts) > 1 else "stripes",
                coverage=parts[2] if len(parts) > 2 else "full"))
        else:
            phenotypes.append(Phenotype(name=label, key=key, is_shading=False,
                color=key, pattern=None, coverage=None))
    return phenotypes


def is_person_affected(person, phenotypes):
    """Check if a person is affected for any phenotype. Returns True/False."""
    if person.fill_mode == "solid" and person.fill_color:
        for ph in phenotypes:
            if not ph.is_shading and ph.color == person.fill_color:
                return True
    if person.fill_mode == "half":
        for c in (person.halves or []):
            if c:
                for ph in phenotypes:
                    if not ph.is_shading and ph.color == c:
                        return True
    if person.fill_mode == "quartered":
        for c in (person.quarters or []):
            if c:
                for ph in phenotypes:
                    if not ph.is_shading and ph.color == c:
                        return True
    if person.fill_mode == "shading":
        shading_key = f"shading:{person.shading_pattern}:{person.shading_coverage}"
        for ph in phenotypes:
            if ph.is_shading and (ph.key == shading_key or ph.pattern == person.shading_pattern):
                return True
    return False


def get_person_diseases(person, phenotypes):
    """Return list of disease label strings this person is affected with."""
    diseases = []
    colours = set()
    if person.fill_mode == "solid" and person.fill_color:
        colours.add(person.fill_color)
    elif person.fill_mode == "half":
        for c in (person.halves or []):
            if c:
                colours.add(c)
    elif person.fill_mode == "quartered":
        for c in (person.quarters or []):
            if c:
                colours.add(c)

    for ph in phenotypes:
        if not ph.is_shading and ph.color in colours:
            diseases.append(ph.name)
        elif ph.is_shading and person.fill_mode == "shading":
            if ph.pattern == person.shading_pattern:
                diseases.append(ph.name)

    return diseases


# ── GA4GH Pedigree output ────────────────────────────────────────────────

def build_ga4gh_pedigree(family, phenotypes, id_map, include_names=False):
    """Build a GA4GH Pedigree Standard JSON document."""
    pship_map = {p.id: p for p in family.partnerships}

    # Build individuals
    individuals = []
    for p in sorted(family.persons.values(), key=lambda x: x.id):
        ind = {
            "id": id_map[p.id],
            "sex": SEX_CODE_TO_GA4GH.get(p.sex, "UNKNOWN_SEX"),
        }
        # Name and DOB from annotation text — only if include_names is True
        if include_names and p.text and p.text.strip():
            parts = p.text.strip().split("\n")
            ind["name"] = parts[0].strip()
            for part in parts:
                dob_match = re.search(r"b\.\s*(\d{4})", part)
                if dob_match:
                    ind["dateOfBirth"] = dob_match.group(1)

        if p.deceased:
            ind["deceased"] = True

        if is_person_affected(p, phenotypes):
            ind["affected"] = True

        individuals.append(ind)

    # Build relationships
    relationships = []
    for cl in family.child_links:
        pship = pship_map.get(cl.partnership_id)
        if not pship:
            continue
        child = family.persons.get(cl.child_id)
        if not child:
            continue

        child_iid = id_map[cl.child_id]

        # Mother relationship
        if child.mother_id and child.mother_id in id_map:
            mother = family.persons.get(child.mother_id)
            if cl.dashed:
                rel = dict(KIN_ADOPTIVE_PARENT_OF)
            else:
                rel = dict(KIN_BIOLOGICAL_MOTHER_OF)
            relationships.append({
                "individual": id_map[child.mother_id],
                "relation": rel,
                "relative": child_iid,
            })

        # Father relationship
        if child.father_id and child.father_id in id_map:
            if cl.dashed:
                rel = dict(KIN_ADOPTIVE_PARENT_OF)
            else:
                rel = dict(KIN_BIOLOGICAL_FATHER_OF)
            relationships.append({
                "individual": id_map[child.father_id],
                "relation": rel,
                "relative": child_iid,
            })

    # Twin relationships
    for tl in family.twin_links:
        if tl.child1_id in id_map and tl.child2_id in id_map:
            if tl.type == "identical":
                rel = dict(KIN_MONOZYGOTIC_TWIN)
            else:
                rel = dict(KIN_DIZYGOTIC_TWIN)
            relationships.append({
                "individual": id_map[tl.child1_id],
                "relation": rel,
                "relative": id_map[tl.child2_id],
            })

    # Index patients (probands)
    index_patients = [id_map[p.id] for p in family.persons.values() if p.proband]

    pedigree = {
        "id": family.family_id,
        "individuals": individuals,
        "relationships": relationships,
        "date": date.today().isoformat(),
    }
    if index_patients:
        pedigree["indexPatients"] = index_patients

    # Add narrative
    pheno_desc = ", ".join(ph.name for ph in phenotypes) if phenotypes else "unspecified"
    pedigree["narrative"] = (
        f"GA4GH Pedigree with {len(individuals)} individuals. "
        f"Conditions tracked: {pheno_desc}."
    )

    return pedigree


# ── Phenopackets output ──────────────────────────────────────────────────

def _make_disease_term(label: str) -> dict:
    """Create a Phenopackets Disease element from a free-text label.

    The OntologyClass `term` uses the label as-is with an empty `id` field.
    For full Phenopackets compliance, downstream tools should map these labels
    to ontology terms (OMIM, Orphanet, MONDO, etc.).
    """
    return {
        "term": {"id": "", "label": label},
    }


def _make_phenotypic_feature(label: str) -> dict:
    """Create a Phenopackets PhenotypicFeature element from a free-text label.

    The OntologyClass `type` uses the label as-is with an empty `id` field.
    For full Phenopackets compliance, downstream tools should map these labels
    to HPO terms (e.g. HP:0000520).
    """
    return {
        "type": {"id": "", "label": label},
    }


def build_phenopackets_family(family, phenotypes, id_map, use_phenotypic_features=False):
    """Build a Phenopackets Family JSON document.

    Contains:
    - A PED-compatible Pedigree (list of Person records)
    - Disease or phenotypic feature information extracted from the legend
    - Proband Phenopacket

    Parameters
    ----------
    use_phenotypic_features : bool
        If True, conditions are recorded as phenotypicFeatures (HPO-style)
        instead of diseases (OMIM/MONDO-style).
    """
    # Helper to create the right element type
    def make_condition(label):
        if use_phenotypic_features:
            return _make_phenotypic_feature(label)
        return _make_disease_term(label)

    # Field name in the Phenopacket
    conditions_field = "phenotypicFeatures" if use_phenotypic_features else "diseases"
    # Build PED-compatible pedigree
    ped_persons = []
    for p in sorted(family.persons.values(), key=lambda x: x.id):
        iid = id_map[p.id]
        father = id_map.get(p.father_id, "0") if p.father_id else "0"
        mother = id_map.get(p.mother_id, "0") if p.mother_id else "0"

        affected = is_person_affected(p, phenotypes)
        status = "AFFECTED" if affected else "UNAFFECTED"

        ped_persons.append({
            "familyId": family.family_id,
            "individualId": iid,
            "paternalId": father,
            "maternalId": mother,
            "sex": SEX_CODE_TO_PHENOPACKET.get(p.sex, "UNKNOWN_SEX"),
            "affectedStatus": status,
        })

    pedigree_block = {"persons": ped_persons}

    # Check consanguinity
    consanguinous = any(ps.type == "consanguineous" for ps in family.partnerships)

    # Find proband
    proband_person = None
    for p in family.persons.values():
        if p.proband:
            proband_person = p
            break
    # Fallback: first affected individual
    if not proband_person:
        for p in family.persons.values():
            if is_person_affected(p, phenotypes):
                proband_person = p
                break
    # Fallback: first individual
    if not proband_person and family.persons:
        proband_person = next(iter(family.persons.values()))

    # Build proband phenopacket
    proband_phenopacket = None
    if proband_person:
        proband_subject = {
            "id": id_map[proband_person.id],
            "sex": SEX_CODE_TO_PHENOPACKET.get(proband_person.sex, "UNKNOWN_SEX"),
        }
        if proband_person.deceased:
            proband_subject["vitalStatus"] = {"status": "DECEASED"}

        proband_conditions = [make_condition(d) for d in get_person_diseases(proband_person, phenotypes)]

        proband_phenopacket = {
            "id": f"{family.family_id}-proband",
            "subject": proband_subject,
        }
        if proband_conditions:
            proband_phenopacket[conditions_field] = proband_conditions

    # Build relative phenopackets — ONLY for affected relatives with disease info.
    # Unaffected relatives and deceased-but-unaffected individuals do not need
    # their own Phenopackets — their status is already in the pedigree block.
    relatives = []
    for p in sorted(family.persons.values(), key=lambda x: x.id):
        if proband_person and p.id == proband_person.id:
            continue
        diseases = get_person_diseases(p, phenotypes)
        if not diseases:
            continue  # no disease info = no Phenopacket needed

        rel_subject = {
            "id": id_map[p.id],
            "sex": SEX_CODE_TO_PHENOPACKET.get(p.sex, "UNKNOWN_SEX"),
        }
        if p.deceased:
            rel_subject["vitalStatus"] = {"status": "DECEASED"}

        rel_packet = {"id": f"{family.family_id}-{id_map[p.id]}", "subject": rel_subject}
        rel_packet[conditions_field] = [make_condition(d) for d in diseases]
        relatives.append(rel_packet)

    # Build metadata
    meta_data = {
        "created": date.today().isoformat() + "T00:00:00Z",
        "createdBy": "studio2ga4gh",
        "resources": [],
    }

    # Assemble Family
    family_doc = {
        "id": family.family_id,
        "pedigree": pedigree_block,
        "metaData": meta_data,
    }
    if proband_phenopacket:
        family_doc["proband"] = proband_phenopacket
    if relatives:
        family_doc["relatives"] = relatives
    if consanguinous:
        family_doc["consanguinousParents"] = True

    return family_doc


# ── Public API ────────────────────────────────────────────────────────────

@dataclass
class ConversionResult:
    files: list  # [(filename, content_string)]
    families: list
    phenotypes: list
    summary: str


def convert(session_data: dict, output_prefix: str = "pedigree",
            use_phenotypic_features: bool = False,
            include_names: bool = False) -> ConversionResult:
    """Convert a Pedigree Studio session to GA4GH Pedigree and Phenopackets files.

    Parameters
    ----------
    use_phenotypic_features : bool
        If True, conditions are recorded as phenotypicFeatures (HPO-style).
    include_names : bool
        If True, names and dates of birth from annotation text are included.
        Default is False (anonymous output).
    """
    persons, partnerships, child_links, twin_links, legend_labels = parse_session(session_data)
    if not persons:
        return ConversionResult(files=[], families=[], phenotypes=[], summary="No persons found.")

    families = detect_families(persons, partnerships, child_links, twin_links)
    for fam in families:
        resolve_parents(fam)

    phenotypes = extract_phenotypes(legend_labels)

    files = []
    for i, fam in enumerate(families):
        suffix = f"_{i + 1}" if len(families) > 1 else ""

        if include_names:
            id_map = {p.id: make_individual_id(p) for p in fam.persons.values()}
        else:
            counter = 0
            id_map = {}
            for p in sorted(fam.persons.values(), key=lambda x: x.id):
                counter += 1
                id_map[p.id] = f"ind-{counter}"

        ga4gh = build_ga4gh_pedigree(fam, phenotypes, id_map, include_names)
        ga4gh_json = json.dumps(ga4gh, indent=2)
        files.append((f"{output_prefix}{suffix}_ga4gh.json", ga4gh_json))

        phenopackets = build_phenopackets_family(fam, phenotypes, id_map, use_phenotypic_features)
        phenopackets_json = json.dumps(phenopackets, indent=2)
        files.append((f"{output_prefix}{suffix}_phenopackets.json", phenopackets_json))

    fam_desc = ", ".join(f"{f.family_id} ({len(f.persons)} individuals)" for f in families)
    pheno_desc = ", ".join(ph.name for ph in phenotypes) if phenotypes else "none"
    condition_type = "phenotypic features" if use_phenotypic_features else "diseases"
    twins = sum(len(f.twin_links) for f in families)
    adopted = sum(1 for f in families for p in f.persons.values() if p.is_adopted)
    anon = "anonymous" if not include_names else "with names"
    summary = (
        f"Converted {len(families)} pedigree(s): {fam_desc}. "
        f"Conditions ({condition_type}): {pheno_desc}. "
        f"Twins: {twins}. Adoptions: {adopted}. Output: {anon}. "
        f"Files: {len(files)} ({len(families)} GA4GH + {len(families)} Phenopackets)."
    )

    return ConversionResult(files=files, families=families, phenotypes=phenotypes, summary=summary)


def convert_file(input_path: str, output_prefix: Optional[str] = None,
                 output_dir: Optional[str] = None,
                 use_phenotypic_features: bool = False,
                 include_names: bool = False) -> ConversionResult:
    """Read a session JSON and write GA4GH + Phenopackets files."""
    with open(input_path, "r") as f:
        session_data = json.load(f)

    if output_prefix is None:
        output_prefix = os.path.splitext(os.path.basename(input_path))[0]
    if output_dir is None:
        output_dir = os.path.dirname(input_path) or "."

    result = convert(session_data, output_prefix, use_phenotypic_features, include_names)

    written = []
    for filename, content in result.files:
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w") as f:
            f.write(content)
        written.append((filepath, content))

    result.files = written
    return result
