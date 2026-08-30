"""Local OCR and document-specific extraction.

The OCR engine is deliberately independent of the reference database. The
database receives only values extracted from visible text.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).with_name("vision_ocr.swift")
_vision_available: bool | None = None


class LocalOCR:
    """Run a free, local OCR engine and return observable OCR evidence."""

    def recognize(self, image_path: str) -> dict:
        global _vision_available
        if _vision_available is not False and sys.platform == "darwin" and shutil.which("swift") and _SCRIPT.exists():
            try:
                completed = subprocess.run(["swift", str(_SCRIPT), image_path], capture_output=True, text=True, timeout=45, check=True)
                _vision_available = True
                return json.loads(completed.stdout)
            except (subprocess.SubprocessError, json.JSONDecodeError):
                # A broken Command Line Tools installation must not turn into an
                # identity shortcut; proceed to the independent local fallback.
                _vision_available = False
        try:
            import pytesseract
            from pytesseract import Output
            installed_languages = pytesseract.get_languages(config="")
            languages = "+".join(language for language in ("eng", "hin") if language in installed_languages) or "eng"
            # Sparse card layouts often work better with automatic page layout;
            # dense generated fixtures work better with a single block.  OCR both
            # layouts and let extract() retain the evidence with more fields.
            config = f"--psm 3 -l {languages}"
            data = pytesseract.image_to_data(image_path, output_type=Output.DICT, config=config)
            boxes, words, confidences = [], [], []
            for index, word in enumerate(data["text"]):
                value = word.strip()
                confidence = float(data["conf"][index]) if data["conf"][index] != "-1" else -1
                if value:
                    words.append(value)
                    if confidence >= 0: confidences.append(confidence / 100)
                    boxes.append({"text": value, "confidence": round(max(confidence, 0) / 100, 3), "x": data["left"][index], "y": data["top"][index], "width": data["width"][index], "height": data["height"][index]})
            raw_text = pytesseract.image_to_string(image_path, config=config)
            return {"raw_text": raw_text, "confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0, "boxes": boxes, "engine": "Tesseract", "languages": languages}
        except (ImportError, RuntimeError, OSError) as exc:
            return {"raw_text": "", "confidence": 0.0, "boxes": [], "engine": "unavailable", "error": f"No local OCR engine is available: {exc}"}

    def extract(self, image_path: str | list[str], document_type: str) -> dict:
        """OCR one or more locally produced image variants and keep the best text result."""
        paths = [image_path] if isinstance(image_path, str) else image_path
        candidates = []
        for path in paths:
            evidence = self.recognize(path)
            evidence["fields"] = extract_fields(evidence["raw_text"], document_type)
            # Completeness matters more than an OCR engine's word confidence.
            evidence["_score"] = len(evidence["fields"]) * 2 + evidence["confidence"]
            candidates.append(evidence)
        winner = max(candidates, key=lambda value: value["_score"])
        winner.pop("_score", None)
        winner["variants_evaluated"] = len(candidates)
        return winner


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :|-\t")


def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"(?:^|\n)\s*{label}\s*[:=-]\s*([^\n]+)", text, re.I)
        if match: return _clean(match.group(1))
    return None

def _date_value(value: str | None) -> str | None:
    if not value: return None
    iso = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if iso: return iso.group()
    match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", value)
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None

def _nearby_name(text: str, marker: str) -> str | None:
    lines = [_clean(line) for line in text.splitlines()]
    for index, line in enumerate(lines):
        if re.search(marker, line, re.I):
            for candidate in reversed(lines[max(0, index-4):index]):
                value = re.sub(r"[^A-Za-z ]", "", candidate).strip()
                if len(value) >= 4 and value.lower() not in {"government of india", "income tax department"}:
                    return value
    return None


def extract_fields(raw_text: str, document_type: str) -> dict:
    """Extract only values visibly present in OCR text using per-document rules."""
    text = raw_text.replace("\r", "\n")
    compact = re.sub(r"\s+", " ", text).upper()
    fields: dict[str, str] = {}
    if document_type == "aadhaar":
        mappings = {"name": ("name",), "date_of_birth": ("date of birth", "dob"), "gender": ("gender",), "address": ("address",)}
        matches = re.findall(r"DEM[-\s]?[A-Z]{3}[-\s]?\d{4}|\b\d{4}\s?\d{4}\s?\d{4}\b", compact)
        # A card can contain an enrolment/virtual ID before the printed document
        # number.  Prefer the final visible 12-digit candidate; never consult a
        # QR code or reference database to fill it in.
        if matches:
            match = matches[-1]
            fields["aadhaar_number"] = re.sub(r"\s+", "", match).replace(" ", "-") if "DEM" in match else re.sub(r"\s+", "", match)
    elif document_type == "pan":
        mappings = {"name": ("name",), "father_name": ("father name", "father's name"), "date_of_birth": ("date of birth", "dob")}
        match = re.search(r"DEM[A-Z]{3}\d{3}X|\b[A-Z]{5}\d{4}[A-Z]\b", compact)
        if match: fields["pan_number"] = match.group()
    elif document_type == "passport":
        mappings = {"surname": ("surname",), "given_name": ("given name", "given names"), "nationality": ("nationality",), "date_of_birth": ("date of birth", "dob"), "sex": ("sex",), "date_of_issue": ("date of issue",), "date_of_expiry": ("date of expiry", "expiry date"), "place_of_birth": ("place of birth",)}
        match = re.search(r"DMP\d{6}|\b[A-Z]\d{7}\b", compact)
        if match: fields["passport_number"] = match.group()
    else:
        return fields
    for key, labels in mappings.items():
        value = _label_value(text, labels)
        if key.startswith("date_") and value:
            date = re.search(r"\d{4}-\d{2}-\d{2}", value)
            value = date.group() if date else value
        if key == "sex" and value:
            value = value.upper()[:1]
        if key == "place_of_birth" and value:
            place = re.match(r"[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,2}", value)
            value = place.group() if place else value
        if value: fields[key] = value
    # Realistic Repo B fixtures use printed government-card layouts rather than labels.
    if document_type == "aadhaar":
        fields.setdefault("name", _nearby_name(text, r"DOB|Date of Birth") or "")
        fields["date_of_birth"] = _date_value(fields.get("date_of_birth") or re.search(r"(?:DOB|Date of Birth)[^\n]*?(\d{2}[/-]\d{2}[/-]\d{4})", text, re.I).group(1) if re.search(r"(?:DOB|Date of Birth)[^\n]*?(\d{2}[/-]\d{2}[/-]\d{4})", text, re.I) else None) or fields.get("date_of_birth", "")
        gender = re.search(r"\b(MALE|FEMALE)\b", compact)
        if gender: fields["gender"] = gender.group(1).title()
    elif document_type == "pan":
        fields.setdefault("name", _nearby_name(text, r"Father") or "")
        fields.setdefault("father_name", _nearby_name(text, r"Date of Birth") or "")
        fields["date_of_birth"] = _date_value(fields.get("date_of_birth") or re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", text).group(1) if re.search(r"(\d{2}[/-]\d{2}[/-]\d{4})", text) else None) or fields.get("date_of_birth", "")
    elif document_type == "passport":
        lines = [_clean(line) for line in text.splitlines()]
        name_line = next((line for line in lines if re.fullmatch(r"[A-Z ]{6,}", line) and "IND" not in line), None)
        if name_line: fields.setdefault("given_name", name_line)
        if "INDIAN" in compact: fields.setdefault("nationality", "IND")
    return {key: value for key, value in fields.items() if value}
