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
            data = pytesseract.image_to_data(image_path, output_type=Output.DICT, config=f"--psm 6 -l {languages}")
            boxes, words, confidences = [], [], []
            for index, word in enumerate(data["text"]):
                value = word.strip()
                confidence = float(data["conf"][index]) if data["conf"][index] != "-1" else -1
                if value:
                    words.append(value)
                    if confidence >= 0: confidences.append(confidence / 100)
                    boxes.append({"text": value, "confidence": round(max(confidence, 0) / 100, 3), "x": data["left"][index], "y": data["top"][index], "width": data["width"][index], "height": data["height"][index]})
            raw_text = pytesseract.image_to_string(image_path, config=f"--psm 6 -l {languages}")
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


def extract_fields(raw_text: str, document_type: str) -> dict:
    """Extract only values visibly present in OCR text using per-document rules."""
    text = raw_text.replace("\r", "\n")
    compact = re.sub(r"\s+", " ", text).upper()
    fields: dict[str, str] = {}
    if document_type == "aadhaar":
        mappings = {"name": ("name",), "date_of_birth": ("date of birth", "dob"), "gender": ("gender",), "address": ("address",)}
        match = re.search(r"DEM[-\s]?[A-Z]{3}[-\s]?\d{4}", compact)
        if match: fields["aadhaar_number"] = re.sub(r"\s+", "", match.group()).replace(" ", "-") if "-" in match.group() else match.group().replace(" ", "")
    elif document_type == "pan":
        mappings = {"name": ("name",), "father_name": ("father name", "father's name"), "date_of_birth": ("date of birth", "dob")}
        match = re.search(r"DEM[A-Z]{3}\d{3}X", compact)
        if match: fields["pan_number"] = match.group()
    elif document_type == "passport":
        mappings = {"surname": ("surname",), "given_name": ("given name", "given names"), "nationality": ("nationality",), "date_of_birth": ("date of birth", "dob"), "sex": ("sex",), "date_of_issue": ("date of issue",), "date_of_expiry": ("date of expiry", "expiry date"), "place_of_birth": ("place of birth",)}
        match = re.search(r"DMP\d{6}", compact)
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
    return fields
