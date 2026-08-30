"""Optional CV detectors that return review evidence, never verdicts."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import cv2
import numpy as np


def _ok(**values):
    return {"enabled": True, "available": True, **values}


def localized_ela(image: np.ndarray) -> dict:
    """Detect unusually local JPEG recompression differences, conservatively."""
    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not success:
        return _ok(score=0.0, suspicious=False, evidence=["ELA encoding was unavailable"])
    recompressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    residual = cv2.cvtColor(cv2.absdiff(image, recompressed), cv2.COLOR_BGR2GRAY)
    smooth = cv2.GaussianBlur(residual, (5, 5), 0)
    threshold = max(3.0, float(smooth.mean() + 3 * smooth.std()))
    mask = (smooth >= threshold).astype(np.uint8)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask)
    regions = sum(1 for area in stats[1:, cv2.CC_STAT_AREA] if area >= 120)
    score = min(100.0, regions * 18.0 + max(0.0, float(smooth.max()) - threshold) * 2.0)
    return _ok(score=round(score, 1), suspicious=bool(regions), suspicious_regions=regions,
               evidence=["Localized compression differences require review"] if regions else [])


def copy_move(image: np.ndarray, overlay_path: Path | None = None) -> dict:
    """ORB/RANSAC repeated-region signal adapted from B without side effects."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = min(1.0, 1400.0 / max(gray.shape))
    work = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
    points, desc = cv2.ORB_create(nfeatures=2000, edgeThreshold=15).detectAndCompute(work, None)
    if desc is None or len(points) < 15:
        return _ok(score=0.0, suspicious=False, keypoints=len(points or []), matches=0, inliers=0, overlay_path=None, evidence=[])
    rows = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(desc, desc, k=min(4, len(desc)))
    minimum = max(30.0, min(work.shape) * .03); candidates = []
    for index, row in enumerate(rows):
        other = [match for match in row if match.trainIdx != index]
        if not other or other[0].distance > 45 or (len(other) > 1 and other[0].distance >= .85 * other[1].distance):
            continue
        first, second = np.array(points[index].pt), np.array(points[other[0].trainIdx].pt)
        if np.linalg.norm(second - first) >= minimum:
            candidates.append((index, other[0].trainIdx, first, second, second - first))
    bins = Counter((round(pair[4][0] / 20), round(pair[4][1] / 20)) for pair in candidates)
    dominant = bins.most_common(1)
    inliers = []
    if dominant:
        key = dominant[0][0]; group = [pair for pair in candidates if (round(pair[4][0] / 20), round(pair[4][1] / 20)) == key]
        if len(group) >= 4:
            src = np.float32([pair[2] for pair in group]).reshape(-1, 1, 2); dst = np.float32([pair[3] for pair in group]).reshape(-1, 1, 2)
            _matrix, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=6)
            inliers = [pair for pair, accepted in zip(group, mask.ravel()) if accepted] if mask is not None else group
    suspicious = len(inliers) >= 6
    saved = None
    if overlay_path and inliers:
        visual = image.copy()
        for pair in inliers[:100]:
            a = tuple(np.round(pair[2] / scale).astype(int)); b = tuple(np.round(pair[3] / scale).astype(int))
            cv2.circle(visual, a, 4, (0, 0, 255), 2); cv2.circle(visual, b, 4, (0, 0, 255), 2); cv2.line(visual, a, b, (0, 0, 255), 1)
        cv2.imwrite(str(overlay_path), visual); saved = str(overlay_path)
    score = min(100.0, len(inliers) * 10.0)
    return _ok(score=round(score, 1), suspicious=suspicious, keypoints=len(points), matches=len(candidates), inliers=len(inliers), overlay_path=saved,
               evidence=["Repeated feature pattern is consistent with possible copy-move editing"] if suspicious else [])


def resampling(image: np.ndarray) -> dict:
    """A low-weight periodic interpolation signal based on Laplacian autocorrelation."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lap = cv2.Laplacian(gray, cv2.CV_32F).mean(axis=0); lap -= lap.mean()
    if len(lap) < 20 or not np.any(lap):
        return _ok(score=0.0, suspicious=False, evidence=[])
    corr = np.correlate(lap, lap, mode="full")[len(lap)-1:]; corr /= max(float(corr[0]), 1e-6)
    peak = float(np.max(corr[2:min(len(corr), 40)]))
    score = min(100.0, max(0.0, (peak - .18) * 220))
    return _ok(score=round(score, 1), suspicious=score >= 45, evidence=["Periodic interpolation artifact signal detected"] if score >= 45 else [])


def jpeg_blocks(image: np.ndarray) -> dict:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    if min(gray.shape) < 32:
        return _ok(score=0.0, suspicious=False, evidence=[])
    vertical = np.abs(np.diff(gray, axis=1)); horizontal = np.abs(np.diff(gray, axis=0))
    boundary = np.mean(vertical[:, 7::8]) + np.mean(horizontal[7::8, :])
    baseline = np.mean(vertical) + np.mean(horizontal)
    score = min(100.0, max(0.0, (boundary / max(baseline, 1e-6) - 1.25) * 90))
    return _ok(score=round(float(score), 1), suspicious=score >= 45, evidence=["JPEG block-boundary inconsistency detected"] if score >= 45 else [])


def edge_inconsistency(image: np.ndarray) -> dict:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    tiles = [np.mean(tile) / 255 * 100 for row in np.array_split(edges, 4) for tile in np.array_split(row, 4, axis=1)]
    spread = float(np.std(tiles)); score = min(100.0, max(0.0, (spread - 8) * 4))
    return _ok(score=round(score, 1), suspicious=score >= 45, evidence=["Unusually uneven edge density detected"] if score >= 45 else [])
