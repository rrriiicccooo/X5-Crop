"""Offline native-pixel measurements centred on confirmed physical boundaries.

Gold locates research windows only. This module never selects a runtime edge,
changes a reference, or treats displaced windows as labelled false boundaries.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Any

import numpy as np

from tools.manual_annotation.imaging import SourceRaster
from tools.manual_annotation.model import canonical_record_sha256
from .file_identity import sha256_file
from .gold_cohort import current_gold_cohort_records, gold_cohort_jsonl
from .accuracy import DEVELOPMENT_GOLD_COHORT_PATH


ROOT = Path(__file__).resolve().parents[2]
REVISION = "confirmed_boundary_native_features_v1"
LUMA = np.asarray((0.2126, 0.7152, 0.0722))
CENTRES_PER_SEGMENT = 24
MAX_RADIUS_PX = 256
TANGENT_OFFSETS = np.arange(-2, 3)


def source_groups(rows: tuple[dict, ...]) -> tuple[tuple[dict, ...], ...]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row['source_sha256']].append(row)
    result = []
    for _sha, members in sorted(groups.items()):
        members.sort(key=lambda r: (-r['count'], r['sample_id']))
        geometry = members[0]['confirmed_geometry']
        for member in members:
            other = member['confirmed_geometry']
            if any(other[key] != geometry[key] for key in ('shared_edges', 'boundary_pool', 'coordinate_system')):
                raise ValueError('same-source tasks disagree on physical geometry')
        result.append(tuple(members))
    return tuple(result)


def intersection(left: dict, right: dict) -> np.ndarray:
    p, q = np.asarray(left['points_raw'], dtype=float)
    r, s = np.asarray(right['points_raw'], dtype=float)
    matrix = np.column_stack((q - p, r - s))
    if abs(np.linalg.det(matrix)) < 1e-9:
        raise ValueError('physical boundary lines do not intersect uniquely')
    return p + np.linalg.solve(matrix, r - p)[0] * (q - p)


def boundary_segments(geometry: dict, axes: str) -> list[dict]:
    """Geometric spans are not human-labelled visible evidence intervals."""
    pool = {line['line_id']: line for line in geometry['boundary_pool']}
    low, high = geometry['shared_edges']
    result = []
    for slot in geometry['slots']:
        pair = slot['reference_geometry']
        if pair['kind'] != 'boundary_pair':
            continue
        start, end = (pool[pair[key]] for key in ('start_boundary_id', 'end_boundary_id'))
        corners = np.asarray([intersection(h, w) for h in (low, high) for w in (start, end)])
        centre = np.mean(corners, axis=0)
        descriptions = []
        if 'H' in axes:
            descriptions.extend(('H', role, line, intersection(line, start), intersection(line, end))
                                for role, line in (('top', low), ('bottom', high)))
        if 'W' in axes:
            descriptions.extend(('W', role, line, intersection(line, low), intersection(line, high))
                                for role, line in (('start', start), ('end', end)))
        for axis, role, line, first, last in descriptions:
            tangent = last - first
            length = float(np.linalg.norm(tangent))
            if length <= 0:
                raise ValueError('empty physical boundary span')
            tangent /= length
            normal = np.asarray((-tangent[1], tangent[0]))
            if np.dot(normal, centre - (first + last) / 2) < 0:
                normal *= -1
            opposite_span = 2 * abs(float(np.dot(normal, centre - (first + last) / 2)))
            result.append(dict(axis=axis, role=role, line=line, ordinal=slot['ordinal'],
                physical_frame_key=(pair['start_boundary_id'], pair['end_boundary_id']),
                slot_kind=slot['slot_kind'], first=first, last=last, tangent=tangent,
                inward_normal=normal, length=length, opposite_span=opposite_span))
    return result


def sample_profiles(raw: np.ndarray, segment: dict) -> tuple[np.ndarray, np.ndarray, int, np.ndarray]:
    if raw.dtype.kind != 'u' or raw.dtype.itemsize != 2 or raw.ndim != 3 or raw.shape[2] != 3:
        raise ValueError('research requires native uint16 RGB pixels')
    radius = min(MAX_RADIUS_PX, max(16, int(np.ceil(segment['opposite_span'] * .05))))
    fractions = (np.arange(CENTRES_PER_SEGMENT) + .5) / CENTRES_PER_SEGMENT
    centres = segment['first'][None, :] + fractions[:, None] * (segment['last'] - segment['first'])
    normal_offsets = np.arange(-radius, radius + 1)
    coordinates = (centres[:, None, None, :] + normal_offsets[None, :, None, None] * segment['inward_normal']
                   + TANGENT_OFFSETS[None, None, :, None] * segment['tangent'])
    lower = np.floor(coordinates).astype(np.int64)
    upper = np.ceil(coordinates).astype(np.int64)
    valid = ((lower[..., 0] >= 0) & (upper[..., 0] < raw.shape[1]) &
             (lower[..., 1] >= 0) & (upper[..., 1] < raw.shape[0]))
    samples = np.full((*valid.shape, 3), np.nan, dtype=float)
    x0, y0 = lower[..., 0][valid], lower[..., 1][valid]
    x1, y1 = upper[..., 0][valid], upper[..., 1][valid]
    dx = (coordinates[..., 0][valid] - x0)[:, None]
    dy = (coordinates[..., 1][valid] - y0)[:, None]
    samples[valid] = ((1 - dx) * (1 - dy) * raw[y0, x0] + dx * (1 - dy) * raw[y0, x1]
                      + (1 - dx) * dy * raw[y1, x0] + dx * dy * raw[y1, x1]) / 65535.0
    # Bilinear raw-pixel sampling avoids orientation-dependent half-pixel ties.
    # Require the complete footprint; never clamp to the TIFF edge.
    complete = np.all(valid, axis=2)
    profiles = np.mean(samples, axis=2)
    profiles[~complete] = np.nan
    tangential_texture = np.mean(np.abs(np.diff(samples @ LUMA, axis=2)), axis=2)
    tangential_texture[~complete] = np.nan
    return profiles, tangential_texture, radius, centres


def feature_rows(profiles: np.ndarray, tangent_texture: np.ndarray, radius: int) -> list[dict]:
    """Retain every fixed displacement and scale; no best-line selection."""
    offsets = np.unique(np.r_[np.arange(-radius // 2, radius // 2 + 1, max(1, radius // 16)), 0])
    scales = [width for width in (2, 4, 8, 16, 32) if 2 * width <= radius // 2]
    result = []
    for offset in offsets:
        centre = radius + int(offset)
        for width in scales:
            outer = profiles[:, centre - width:centre]
            inner = profiles[:, centre + 1:centre + width + 1]
            outer_far = profiles[:, centre - 2 * width:centre - width]
            inner_far = profiles[:, centre + width + 1:centre + 2 * width + 1]
            valid = np.all(np.isfinite(np.concatenate((outer_far, outer, inner, inner_far), axis=1)), axis=(1, 2))
            delta = np.mean(inner, axis=1) - np.mean(outer, axis=1)
            far_delta = np.mean(inner_far, axis=1) - np.mean(outer_far, axis=1)
            tone = delta @ LUMA
            far_tone = far_delta @ LUMA
            outer_gray, inner_gray = outer @ LUMA, inner @ LUMA
            outer_texture = np.mean(np.abs(np.diff(outer_gray, axis=1)), axis=1)
            inner_texture = np.mean(np.abs(np.diff(inner_gray, axis=1)), axis=1)
            variation = np.maximum(np.std(outer_gray, axis=1), np.std(inner_gray, axis=1))
            texture_slice = tangent_texture[:, centre - width:centre + width + 1]
            values = dict(
                outside_gray=np.mean(outer_gray, axis=1), inside_gray=np.mean(inner_gray, axis=1),
                signed_gray_change=tone, rgb_change=np.linalg.norm(delta, axis=1) / np.sqrt(3.),
                opponent_color_change=np.linalg.norm(delta[:, (0, 2)] - delta[:, 1, None], axis=1) / np.sqrt(2.),
                outside_normal_texture=outer_texture, inside_normal_texture=inner_texture,
                tangent_texture=np.mean(texture_slice, axis=1),
                contrast_over_local_variation=np.abs(tone) / np.maximum(variation, 1. / 65535.),
                signed_far_gray_change=far_tone,
                persistent_same_polarity=(tone * far_tone > 0).astype(float),
                outside_smoother=(outer_texture < inner_texture).astype(float),
            )
            result.append(dict(offset_inward_px=int(offset), window_px=width,
                valid=valid.tolist(), values={name: [float(v) if ok else None for v, ok in zip(array, valid, strict=True)]
                                            for name, array in values.items()}))
    return result


def inventory(groups: tuple[tuple[dict, ...], ...]) -> dict:
    bases: dict[str, Counter] = {'H': Counter(), 'W': Counter()}
    for members in groups:
        geometry = members[0]['confirmed_geometry']
        active = {s['reference_geometry'][key] for s in geometry['slots']
                  if s['reference_geometry']['kind'] == 'boundary_pair'
                  for key in ('start_boundary_id', 'end_boundary_id')}
        bases['H'].update(line['review_basis'] for line in geometry['shared_edges'])
        bases['W'].update(line['review_basis'] for line in geometry['boundary_pool'] if line['line_id'] in active)
    return dict(task_count=sum(map(len, groups)), source_count=len(groups),
        physical_boundary_review_bases={axis: dict(count) for axis, count in bases.items()},
        source_groups=[dict(source_sha256=m[0]['source_sha256'], sample_ids=[r['sample_id'] for r in m],
                           development_fold=int(hashlib.sha256(m[0]['source_sha256'].encode()).hexdigest(), 16) % 5)
                       for m in groups],
        evaluation_scope='development_only_no_unseen_or_sealed_claim',
        fold_scope='source_grouped_future_analysis_partition_not_a_historical_holdout')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--sample-id', action='append')
    parser.add_argument('--axes', choices=('H', 'W', 'HW'), default='H')
    args = parser.parse_args(argv)
    output = args.output_root.resolve()
    if not output.is_relative_to((ROOT / 'Test').resolve()):
        parser.error('research artifacts must stay in ignored Test/')
    # Full authority audit precedes sampling; no write/promotion operation.
    rows = current_gold_cohort_records()
    if DEVELOPMENT_GOLD_COHORT_PATH.read_text() != gold_cohort_jsonl(rows):
        raise ValueError('tracked gold is not the current confirmed derivation')
    groups = source_groups(rows)
    selected = set(args.sample_id or ())
    if selected - {r['sample_id'] for r in rows}:
        parser.error('unknown sample id')
    output.mkdir(parents=True, exist_ok=True)
    summary = dict(revision=REVISION, **inventory(groups), axes=args.axes,
        cohort_sha256=sha256_file(DEVELOPMENT_GOLD_COHORT_PATH),
        tool_sha256=sha256_file(Path(__file__)),
        dependencies={name: importlib.metadata.version(name) for name in ('numpy', 'tifffile')},
        sampling=dict(centres_per_frame_segment=CENTRES_PER_SEGMENT, tangent_offsets_px=TANGENT_OFFSETS.tolist(),
                      radius='min(256, max(16, ceil(0.05 * opposing_frame_span)))',
                      stored_rgb='native uint16 / 65535; no ICC conversion or local contrast stretch',
                      coordinates='raw TIFF; bilinear native-pixel samples; positive normal is inward'),
        limitations=['No along-line visibility annotation exists.',
                     'Displaced windows are unadjudicated comparisons, not negative labels.',
                     'Material continuity descriptors do not prove material identity.',
                     'Shared/contact lines and all same-source tasks share one source group.',
                     'H acceptance precedes W implementation; no runtime changes.'],
        sampled_sources=[])
    for members in groups:
        if selected and not selected.intersection(r['sample_id'] for r in members):
            continue
        record = members[0]
        source = ROOT / record['source_relative_path']
        before = source.stat()
        if sha256_file(source) != record['source_sha256']:
            raise ValueError('source bytes changed after authority audit')
        segments = boundary_segments(record['confirmed_geometry'], args.axes)
        target = output / (record['source_sha256'] + '.jsonl')
        with SourceRaster(source) as raster, target.open('w') as stream:
            if raster.orientation != record['confirmed_geometry']['coordinate_system']['orientation_mapping']['original_tag']:
                raise ValueError('source orientation disagrees with confirmed coordinates')
            for segment in segments:
                profiles, texture, radius, centres = sample_profiles(raster.raw, segment)
                row = dict(source_sha256=record['source_sha256'], sample_ids=[r['sample_id'] for r in members],
                    geometry_digest=canonical_record_sha256(record['confirmed_geometry']),
                    axis=segment['axis'], role=segment['role'], line_id=segment['line']['line_id'],
                    review_basis=segment['line']['review_basis'], slot_ordinal=segment['ordinal'], slot_kind=segment['slot_kind'],
                    physical_frame_key=list(segment['physical_frame_key']),
                    points_raw=segment['line']['points_raw'], inward_normal_raw=segment['inward_normal'].tolist(),
                    centres_raw=centres.tolist(), radius_px=radius,
                    adjacencies=record['confirmed_geometry']['adjacencies'],
                    profile_rgb=[[([float(c) for c in rgb] if np.all(np.isfinite(rgb)) else None) for rgb in trace] for trace in profiles],
                    features=feature_rows(profiles, texture, radius))
                stream.write(json.dumps(row, allow_nan=False, separators=(',', ':')) + '\n')
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('source changed during research sampling')
        summary['sampled_sources'].append(dict(source_sha256=record['source_sha256'], sample_ids=[r['sample_id'] for r in members],
            segment_count=len(segments), artifact=target.name, artifact_sha256=sha256_file(target)))
        print('/'.join(r['sample_id'] for r in members), len(segments), 'native boundary segments', flush=True)
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
