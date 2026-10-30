"""Tests for studio2ga4gh: the example drawings make valid GA4GH files, and each symbol means what it should.

The drawings in tests/data are fictional families: four from the Hearn lab's pedigree practical, and one
(features.studio.json) with every kind of symbol and line Pedigree Studio draws.
"""
import contextlib
import io
import json
import os
from collections import Counter

import studio2ga4gh
from pedigree_ga4gh import loads, validate
from studio2ga4gh.cli import main
from studio2ga4gh.session import parse

DATA = os.path.join(os.path.dirname(__file__), "data")
CREATED = "2026-10-17T12:00:00Z"
EXAMPLES = ["okafor", "price", "lynch", "cf-cousins"]


def session(name):
    with open(os.path.join(DATA, name + ".studio.json"), encoding="utf-8") as fh:
        return json.load(fh)


def terms():
    with open(os.path.join(DATA, "example-terms.json"), encoding="utf-8") as fh:
        return json.load(fh)


def errors(doc):
    return [f for f in validate(doc) if f.severity == "error"]


def convert(name, **kw):
    r = studio2ga4gh.convert(session(name), name, terms=terms(), created=CREATED, **kw)
    return r, loads(r.files[0][1]), loads(r.files[1][1])


def rels(doc):
    return {(r["individualId"], r["relation"]["label"], r["relativeId"]) for r in doc["relationships"]}


def test_examples_convert_to_valid_files():
    for name in EXAMPLES:
        r, ped, fam = convert(name)
        assert r.unmatched == [], name
        assert errors(ped) == [] and errors(fam) == [], name
        assert ped["individuals"] and fam["pedigree"]["persons"]
        assert [n for n, _ in r.files] == [name + "_ga4gh-pedigree.json", name + "_phenopackets-family.json"]


def test_ids_are_the_pedigree_numbers_studio_shows():
    s = parse(session("okafor"))
    nums = s.numbers()
    assert sorted(set(v.split("-")[0] for v in nums.values())) == ["I", "II", "III", "IV"]
    r, ped, fam = convert("okafor")
    ids = [i["subject"]["id"] for i in ped["individuals"]]
    assert set(ids) <= set(nums.values()) and len(set(ids)) == len(ids)
    assert ped["indexPatients"] == ["IV-3"]
    # the drawing's own labels, or the Studio's ids, when asked for
    r, ped, fam = convert("okafor", ids="studio")
    assert {i["subject"]["id"] for i in ped["individuals"]} <= set(s.persons)


def test_conditions_without_a_term_are_left_out_with_a_note():
    r = studio2ga4gh.convert(session("okafor"), "okafor", created=CREATED)
    ped = loads(r.files[0][1])
    assert set(r.unmatched) == {"Breast cancer", "Hearing loss from birth"}
    assert "left out" in r.summary
    assert errors(ped) == []
    assert not any(i.get("diseases") or i.get("phenotypicFeatures") for i in ped["individuals"])


def test_terms_decide_disease_or_phenotype():
    r, ped, fam = convert("okafor")
    by_id = {i["subject"]["id"]: i for i in ped["individuals"]}
    assert [f["type"]["id"] for f in by_id["IV-3"]["phenotypicFeatures"]] == ["HP:0000365"]
    assert [d["term"]["id"] for d in by_id["II-3"]["diseases"]] == ["MONDO:0007254"]
    res = {r_["namespacePrefix"]: r_["version"] for r_ in by_id["II-3"]["metaData"]["resources"]}
    assert res == {"MONDO": "2026-10-06"}


def test_features_drawing():
    r = studio2ga4gh.convert(session("features"), "features", created=CREATED)
    ped, fam = loads(r.files[0][1]), loads(r.files[1][1])
    assert errors(ped) == [] and errors(fam) == []
    got = rels(ped)
    labels = Counter(lab for _, lab, _ in got)
    # gestational carrier (S, in this older drawing) and donor marks
    assert labels["isGestationalCarrierOf"] == 1 and labels["isSpermDonorOf"] == 1
    # dashed line and the adopted symbol
    assert labels["isAdoptiveParentOf"] == 2
    # separated, consanguineous-separated, and couples whose only "children" are markers
    assert labels["isSeparatedPartnerOf"] == 1 and labels["isSeparatedConsanguineousPartnerOf"] == 1
    assert labels["isPartnerOf"] == 2
    # parent of unknown sex
    assert labels["isBiologicalParentOf"] == 2
    # triplets: c2-c3 identical, c3-c4 non-identical, all given relative to the leftmost
    twins = [(a, lab, b) for a, lab, b in got if "MultipleBirth" in lab]
    assert len(twins) == 2 and len({a for a, _, _ in twins}) == 1
    assert {lab for _, lab, _ in twins} == {"isMonozygoticMultipleBirthSiblingOf",
                                            "isPolyzygoticMultipleBirthSiblingOf"}
    # markers are not people
    assert len(ped["individuals"]) == 27
    narrative = ped["narrative"]
    for words in ("no children", "infertility", "pregnancy loss", "is a carrier", "presymptomatic carrier",
                  "is a pregnancy"):
        assert words in narrative, words
    # the CURIE written in the colour key is used; unnamed conditions are reported
    assert "Condition X [MONDO:0009061]" not in r.unmatched
    assert set(r.unmatched) == {"Condition Y", "Condition Z"}
    proband = fam["proband"]
    assert proband["diseases"][0]["term"]["id"] == "MONDO:0009061"
    # the gestational carrier is not the child's mother in the PED-style pedigree
    persons = {p["individualId"]: p for p in fam["pedigree"]["persons"]}
    carried = [b for a, lab, b in got if lab == "isGestationalCarrierOf"][0]
    carrier = [a for a, lab, b in got if lab == "isGestationalCarrierOf"][0]
    assert persons[carried]["maternalId"] != carrier
    assert any("stands for 3 people" in w for w in r.warnings)
    assert any("does not name" in w for w in r.warnings)


def _features_with(change):
    data = session("features")
    change(data)
    r = studio2ga4gh.convert(data, "features", created=CREATED)
    ped = loads(r.files[0][1])
    assert errors(ped) == [] and errors(loads(r.files[1][1])) == []
    return r, ped


def test_g_marks_a_gestational_carrier():
    """Since the 2025 correction to the nomenclature, the Studio marks a gestational carrier G; S, in older
    drawings, means the same, and both give the same files."""
    def to_g(data):
        [p for p in data["persons"] if p.get("centerText") == "S"][0]["centerText"] = "G"
    r, ped = _features_with(to_g)
    got = rels(ped)
    assert Counter(lab for _, lab, _ in got)["isGestationalCarrierOf"] == 1
    assert got == rels(loads(studio2ga4gh.convert(session("features"), "features", created=CREATED).files[0][1]))
    fam = loads(r.files[1][1])
    persons = {p["individualId"]: p for p in fam["pedigree"]["persons"]}
    carrier, _, carried = [t for t in got if t[1] == "isGestationalCarrierOf"][0]
    assert persons[carried]["maternalId"] != carrier


def _twins(ped):
    return {(a, b): lab for a, lab, b in rels(ped) if "MultipleBirth" in lab}


def _set_twins(kinds):
    def change(data):
        for t, kind in zip(data["twinLinks"], kinds):
            t["type"] = kind
    return change


def test_twins_of_unknown_zygosity():
    """The Studio's "Not known (?)" twins are isMultipleBirthSiblingOf, which says nothing of zygosity. Twins
    joined only through a third get the zygosity that the chain of twin lines gives."""
    # the features triplets: c2-c3 and c3-c4 are joined, c2 is the leftmost
    _, ped = _features_with(_set_twins(["identical", "unknown"]))
    pairs = _twins(ped)
    assert len(pairs) == 2 and len({a for a, _ in pairs}) == 1
    first = next(iter(pairs))[0]
    labels = sorted(pairs.values())
    assert labels == ["isMonozygoticMultipleBirthSiblingOf", "isMultipleBirthSiblingOf"]   # c3; c4 through c3
    _, ped = _features_with(_set_twins(["unknown", "unknown"]))
    assert set(_twins(ped).values()) == {"isMultipleBirthSiblingOf"}
    _, ped = _features_with(_set_twins(["unknown", "nonidentical"]))
    assert set(_twins(ped).values()) == {"isMultipleBirthSiblingOf"}
    # a set drawn as non-identical twins stays non-identical, as before
    _, ped = _features_with(_set_twins(["nonidentical", "nonidentical"]))
    assert set(_twins(ped).values()) == {"isPolyzygoticMultipleBirthSiblingOf"}
    # identical twins of each other are identical, however they are joined
    _, ped = _features_with(_set_twins(["identical", "identical"]))
    assert set(_twins(ped).values()) == {"isMonozygoticMultipleBirthSiblingOf"}
    assert first


def test_a_consultand_is_noted_in_the_narrative():
    """The consultand (an arrow without a P) has no place of its own in the GA4GH files: the narrative says who."""
    def mark(data):
        [p for p in data["persons"] if p["id"] == "gm"][0]["consultand"] = True
    r, ped = _features_with(mark)
    assert " is a consultand." in ped["narrative"]
    assert sum(" is a consultand" in n for n in r.notes) == 1
    plain = loads(studio2ga4gh.convert(session("features"), "features", created=CREATED).files[0][1])
    assert "consultand" not in plain["narrative"]


def test_notes_keep_ids_as_they_are():
    """Pedigree Studio's own ids are in lower case (p6, c1): a note about one must not capitalise it."""
    data = session("features")
    carriers = [p["id"] for p in data["persons"] if p.get("centerText") == "dot"]
    r = studio2ga4gh.convert(data, "features", ids="studio", created=CREATED)
    narrative = loads(r.files[0][1])["narrative"]
    assert carriers and all("{} is a carrier.".format(c) in narrative for c in carriers)
    assert all(c.upper() not in narrative.split() for c in carriers)


def test_only_an_ontologys_id_in_the_key_counts():
    """An id in brackets after a condition counts only if pedigree-ga4gh can declare its ontology: a blood
    pressure in brackets is part of the name, so the condition is left out as unmatched, not given an id."""
    from studio2ga4gh.converter import split_key_label
    assert split_key_label("Breast cancer [MONDO:0007254]") == ("Breast cancer", "MONDO:0007254")
    assert split_key_label("Deafness (hp:0000365)") == ("Deafness", "HP:0000365")
    assert split_key_label("Hypertension (BP:160/95)") == ("Hypertension (BP:160/95)", None)
    drawing = session("price")
    first = next(iter(drawing["legendLabels"]))
    drawing["legendLabels"][first] = "Hypertension (BP:160/95)"
    r = studio2ga4gh.convert(drawing, "price", created=CREATED)
    assert "Hypertension (BP:160/95)" in r.unmatched
    for _, text in r.files:
        assert "BP:160" not in text.replace("Hypertension (BP:160/95)", "") and errors(loads(text)) == []


def test_labels_become_ids_as_in_studio2ped():
    """--ids drawing and --ids studio make ids from labels by studio2ped's rule (J. Mensah -> J_Mensah); an id
    that would be empty, 0 or shared falls back to the pedigree number, with a note."""
    from studio2ga4gh.converter import make_id
    assert make_id("J. Mensah") == "J_Mensah" and make_id("  Ama  Owusu (b. 1950) ") == "Ama_Owusu_b_1950"
    person = lambda pid, shape, x, y, label: {"id": pid, "shape": shape, "x": x, "y": y, "customLabel": label}
    drawing = {"numberingMode": "freetext", "persons": [
        person("f", "male", 0, 0, "J. Mensah"), person("m", "female", 100, 0, "0"),
        person("c1", "male", 0, 150, "Kid"), person("c2", "female", 100, 150, "Kid"),
        person("c3", "male", 200, 150, "?!")],
        "partnerships": [{"id": "pr", "fromId": "f", "toId": "m"}],
        "childLinks": [{"id": "l" + c, "partnershipId": "pr", "childId": c} for c in ("c1", "c2", "c3")]}
    r = studio2ga4gh.convert(drawing, "t", ids="drawing", created=CREATED)
    fam = loads(r.files[1][1])
    persons = {p["individualId"]: p for p in fam["pedigree"]["persons"]}
    assert set(persons) == {"J_Mensah", "I-2", "II-1", "II-2", "II-3"}
    assert persons["II-1"]["paternalId"] == "J_Mensah" and persons["II-1"]["maternalId"] == "I-2"
    assert errors(fam) == [] and errors(loads(r.files[0][1])) == []
    assert any("labelled 0" in w for w in r.warnings)
    assert any("'Kid'" in w for w in r.warnings)
    assert any("II-3's label" in w for w in r.warnings)


def test_names_are_never_written():
    for name in EXAMPLES + ["features"]:
        drawing = session(name)
        texts = {(p.get("text") or "").strip() for p in drawing["persons"]} - {""}
        r = studio2ga4gh.convert(drawing, name, terms=terms(), created=CREATED, ids="numbers")
        written = "".join(text for _, text in r.files)
        for t in texts:
            first = t.split("\n")[0].strip()
            if len(first) > 3 and not first[0].isdigit():
                assert first not in written, (name, first)


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def test_command_line(tmp_path):
    src = os.path.join(DATA, "okafor.studio.json")
    code, out, err = run_cli(src, "-t", os.path.join(DATA, "example-terms.json"), "-d", str(tmp_path))
    assert code == 0, err
    written = sorted(os.listdir(tmp_path))
    assert written == ["okafor_ga4gh-pedigree.json", "okafor_phenopackets-family.json"]
    for f in written:
        with open(os.path.join(tmp_path, f), encoding="utf-8") as fh:
            assert errors(loads(fh.read())) == []
    code, out, err = run_cli(src, "-d", str(tmp_path), "-o", "only", "--only", "family")
    assert code == 0 and os.path.exists(os.path.join(tmp_path, "only_phenopackets-family.json"))
    assert not os.path.exists(os.path.join(tmp_path, "only_ga4gh-pedigree.json"))
    # version 0.3's options still run
    code, out, err = run_cli(src, "-d", str(tmp_path), "-o", "old", "--phenotypes", "--include-names")
    assert code == 0 and os.path.exists(os.path.join(tmp_path, "old_ga4gh-pedigree.json"))
    code, out, err = run_cli(os.path.join(DATA, "no-such-file.json"))
    assert code == 1 and "cannot find" in err
    # a folder that does not exist yet is made
    code, out, err = run_cli(src, "-d", str(tmp_path / "new" / "folder"))
    assert code == 0 and os.path.exists(os.path.join(tmp_path, "new", "folder", "okafor_ga4gh-pedigree.json"))
    # a terms file that is missing or not JSON gives a message, not a traceback
    code, out, err = run_cli(src, "-d", str(tmp_path), "-t", str(tmp_path / "no-terms.json"))
    assert code == 1 and "cannot find the terms file" in err
    bad = tmp_path / "bad-terms.json"
    bad.write_text("{not json", encoding="utf-8")
    code, out, err = run_cli(src, "-d", str(tmp_path), "-t", str(bad))
    assert code == 1 and "could not read the terms file" in err
