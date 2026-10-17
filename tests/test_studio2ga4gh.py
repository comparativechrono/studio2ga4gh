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
    # surrogate and donor marks
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
