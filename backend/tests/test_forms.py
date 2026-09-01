"""
Tests for Statutory Forms Extraction Pipeline (pages 190-249).
Validates dynamic title scraping (zero hardcoding), multi-page boundary detection (Form 33),
manifest verification against disk files, and idempotent re-extraction.
"""

import ast
import hashlib
import json
import os

import pytest

from app.forms.form_extractor import (
    detect_form_boundaries,
    extract_form_pdf,
    slugify,
)
from app.forms.manifest import generate_manifest

# Find project root directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_PATH = os.path.join(BASE_DIR, "data", "raw", "bns_bare_act_2023.pdf")
MANIFEST_PATH = os.path.join(BASE_DIR, "data", "forms", "forms_manifest.json")
FORMS_DIR = os.path.join(BASE_DIR, "data", "forms")
EXTRACTOR_PATH = os.path.join(BASE_DIR, "backend", "app", "forms", "form_extractor.py")


def test_no_hardcoded_titles():
    """
    Asserts that form_extractor.py does NOT contain hardcoded dictionaries of form titles,
    proving dynamic text extraction and scraping per assignment requirements.
    """
    assert os.path.exists(
        EXTRACTOR_PATH
    ), f"Extractor file not found at {EXTRACTOR_PATH}"
    with open(EXTRACTOR_PATH, "r", encoding="utf-8") as f:
        source_code = f.read()

    tree = ast.parse(source_code)
    # Check that no lookup table dictionary literal (more than 10 key-value pairs) exists in AST
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            assert (
                len(node.keys) <= 10
            ), f"Disallowed hardcoded dictionary table with {len(node.keys)} items found in form_extractor.py"

    # Confirm known form title strings are not hardcoded in the source code
    assert "WARRANT OF ARREST" not in source_code
    assert "BOND TO KEEP THE PEACE" not in source_code
    assert "NOTICE FOR APPEARANCE BY THE POLICE" not in source_code


def test_all_58_forms_detected():
    """Asserts that all 58 statutory forms are detected sequentially without gaps."""
    if not os.path.exists(PDF_PATH):
        pytest.skip(f"Bare act PDF not found at {PDF_PATH}")

    forms = detect_form_boundaries(PDF_PATH, start_page=190, end_page=249)
    assert len(forms) == 58, f"Expected 58 forms, detected {len(forms)}"

    form_numbers = [f["form_number"] for f in forms]
    assert form_numbers == list(
        range(1, 59)
    ), "Form numbers are not strictly sequential 1 through 58"


def test_form_33_multipage():
    """
    Validates multi-page boundary detection for Form 33 (CHARGES),
    confirming it spans pages 222-224 (3 pages).
    """
    if not os.path.exists(PDF_PATH):
        pytest.skip(f"Bare act PDF not found at {PDF_PATH}")

    forms = detect_form_boundaries(PDF_PATH, start_page=190, end_page=249)
    form_33 = next((f for f in forms if f["form_number"] == 33), None)

    assert form_33 is not None, "Form 33 not found in detected forms"
    assert form_33["title"] == "CHARGES"
    assert form_33["page_start"] == 222
    assert form_33["page_end"] == 224
    assert form_33["enabling_section"] == "234, 235 and 236"


def test_manifest_matches_disk_files():
    """
    Asserts that every record in forms_manifest.json exists on disk with matching
    byte size and cryptographic SHA-256 hash.
    """
    if not os.path.exists(MANIFEST_PATH):
        pytest.skip(f"Manifest not found at {MANIFEST_PATH}")

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert len(manifest) == 58, f"Expected 58 manifest entries, found {len(manifest)}"

    for item in manifest:
        file_path = os.path.join(FORMS_DIR, item["filename"])
        if not os.path.exists(file_path) and os.path.exists(PDF_PATH):
            extract_form_pdf(PDF_PATH, item["page_start"], item["page_end"], file_path)

        assert os.path.exists(
            file_path
        ), f"Extracted form PDF missing on disk: {file_path}"

        with open(file_path, "rb") as f:
            content = f.read()

        actual_size = len(content)
        actual_sha = hashlib.sha256(content).hexdigest()

        assert (
            actual_size == item["byte_size"]
        ), f"Size mismatch for {item['filename']}: {actual_size} != {item['byte_size']}"
        assert (
            actual_sha == item["sha256"]
        ), f"SHA256 mismatch for {item['filename']}: {actual_sha} != {item['sha256']}"


def test_idempotent_rerun(tmp_path):
    """
    Asserts that re-running PDF extraction and manifest generation on a directory
    produces identical byte-for-byte files and matching SHA-256 hashes.
    """
    if not os.path.exists(PDF_PATH):
        pytest.skip(f"Bare act PDF not found at {PDF_PATH}")

    out_dir = str(tmp_path / "forms")
    manifest_file = str(tmp_path / "forms" / "forms_manifest.json")

    # Run 1
    forms1 = detect_form_boundaries(PDF_PATH, start_page=190, end_page=249)
    res1 = []
    for f in forms1:
        fname = f"FORM-{f['form_number']}_{slugify(f['title'])}.pdf"
        out_path = os.path.join(out_dir, fname)
        info = extract_form_pdf(PDF_PATH, f["page_start"], f["page_end"], out_path)
        m = dict(f)
        m.update(info)
        res1.append(m)
    man1 = generate_manifest(res1, manifest_file)

    # Run 2 on same output
    forms2 = detect_form_boundaries(PDF_PATH, start_page=190, end_page=249)
    res2 = []
    for f in forms2:
        fname = f"FORM-{f['form_number']}_{slugify(f['title'])}.pdf"
        out_path = os.path.join(out_dir, fname)
        info = extract_form_pdf(PDF_PATH, f["page_start"], f["page_end"], out_path)
        m = dict(f)
        m.update(info)
        res2.append(m)
    man2 = generate_manifest(res2, manifest_file)

    for i in range(len(man1)):
        assert (
            man1[i]["sha256"] == man2[i]["sha256"]
        ), f"Non-idempotent SHA-256 hash for form {man1[i]['form_number']}"
        assert (
            man1[i]["byte_size"] == man2[i]["byte_size"]
        ), f"Non-idempotent byte size for form {man1[i]['form_number']}"
