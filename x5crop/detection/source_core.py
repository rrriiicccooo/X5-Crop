from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
import numpy as np

from ..configuration.content import ContentConfiguration
from ..domain import (
    Box,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from .evidence.scan_canvas import ScanCanvasEvidence, ScanCanvasOutcome


@dataclass(frozen=True)
class SourceStripValidationDomain:
    lane_id: str
    work_box: Box
    source_axis_long: str
    authority_profile_id: str

    def __post_init__(self) -> None:
        if not self.lane_id or not self.work_box.valid():
            raise ValueError("source strip domain requires one non-empty lane")
        if self.source_axis_long not in {"x", "y"}:
            raise ValueError("source strip domain requires a source long axis")
        if not self.authority_profile_id:
            raise ValueError("source strip domain requires profile authority")


@dataclass(frozen=True)
class SourceContentComponent:
    component_id: str
    row_run_offset: int
    row_run_count: int
    footprint: Box
    positive_cells: int
    censored: bool
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            not self.component_id
            or self.row_run_offset < 0
            or self.row_run_count <= 0
            or not self.footprint.valid()
            or self.positive_cells <= 0
        ):
            raise ValueError("source content component requires positive evidence")
        if self.provenance.root_measurement != MeasurementIdentity.SOURCE_CONTENT:
            raise ValueError("source content requires source-content provenance")


@dataclass(frozen=True)
class ContentRowRunTable:
    rows: np.ndarray
    lefts: np.ndarray
    rights: np.ndarray
    component_indices: np.ndarray

    def __post_init__(self) -> None:
        arrays = (
            self.rows,
            self.lefts,
            self.rights,
            self.component_indices,
        )
        if any(
            not isinstance(array, np.ndarray)
            or array.ndim != 1
            or array.dtype != np.int32
            for array in arrays
        ):
            raise TypeError("content run table requires one-dimensional int32 arrays")
        if len({array.size for array in arrays}) != 1:
            raise ValueError("content run table arrays must have equal length")
        if np.any(self.rights <= self.lefts):
            raise ValueError("content run table requires positive half-open spans")
        if any(array.flags.writeable for array in arrays):
            raise ValueError("content run table must be immutable")

    @property
    def run_count(self) -> int:
        return int(self.rows.size)


@dataclass(frozen=True)
class SourceContentMeasurementStatistics:
    domain_pixels: int
    streaming_block_count: int
    intensity_active_cells: int
    texture_active_cells: int
    positive_cells: int
    run_count: int
    raw_component_count: int
    component_count: int
    censored_component_count: int
    deterministic_seconds: float
    peak_temporary_bytes: int

    def __post_init__(self) -> None:
        counts = (
            self.domain_pixels,
            self.streaming_block_count,
            self.intensity_active_cells,
            self.texture_active_cells,
            self.positive_cells,
            self.run_count,
            self.raw_component_count,
            self.component_count,
            self.censored_component_count,
            self.peak_temporary_bytes,
        )
        if any(value < 0 for value in counts):
            raise ValueError("source content statistics cannot be negative")
        if self.censored_component_count > self.component_count:
            raise ValueError("censored component count exceeds total components")
        if self.component_count > self.raw_component_count:
            raise ValueError("retained component count exceeds raw components")
        if not np.isfinite(self.deterministic_seconds) or self.deterministic_seconds < 0:
            raise ValueError("source content duration must be finite")


@dataclass(frozen=True)
class SourceContentObservation:
    lane_id: str
    state: EvidenceState
    intensity_threshold: float | None
    texture_threshold: float | None
    components: tuple[SourceContentComponent, ...]
    row_run_table: ContentRowRunTable
    statistics: SourceContentMeasurementStatistics
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.provenance.root_measurement != MeasurementIdentity.SOURCE_CONTENT:
            raise ValueError("content observation has the wrong provenance")
        supported = self.state == EvidenceState.SUPPORTED
        if supported != (
            self.intensity_threshold is not None
            and self.texture_threshold is not None
        ):
            raise ValueError("supported content requires two frozen thresholds")
        if not supported and self.components:
            raise ValueError("unavailable content cannot carry components")
        if not supported and self.row_run_table.run_count:
            raise ValueError("unavailable content cannot carry row runs")
        identities = tuple(component.component_id for component in self.components)
        if len(set(identities)) != len(identities):
            raise ValueError("source content component identities must be unique")
        expected_offset = 0
        for index, component in enumerate(self.components):
            if component.row_run_offset != expected_offset:
                raise ValueError("content component run spans must be contiguous")
            stop = expected_offset + component.row_run_count
            if stop > self.row_run_table.run_count or np.any(
                self.row_run_table.component_indices[expected_offset:stop]
                != index
            ):
                raise ValueError("content component run ownership is inconsistent")
            expected_offset = stop
        if expected_offset != self.row_run_table.run_count:
            raise ValueError("content run table has unowned rows")


@dataclass(frozen=True)
class SourceLaneEvidence:
    domain: SourceStripValidationDomain
    scan_canvas: ScanCanvasEvidence
    content: SourceContentObservation

    def __post_init__(self) -> None:
        if self.scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED:
            raise ValueError("source lane requires unique scan-canvas authority")
        if self.scan_canvas.axis_scales is None:
            raise ValueError("source lane requires scan-canvas scale intervals")
        if self.domain.lane_id != self.content.lane_id:
            raise ValueError("source lane content must share the lane identity")

    @property
    def axis_scale_intervals(self):
        """Borrowed read-only scale intervals; ScanCanvasEvidence remains owner."""
        return self.scan_canvas.axis_scales


@dataclass(frozen=True)
class SourceCoreEvidence:
    lanes: tuple[SourceLaneEvidence, ...]
    incomplete_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(set(lane.domain.lane_id for lane in self.lanes)) != len(self.lanes):
            raise ValueError("source-core lane identities must be unique")
        if len(set(self.incomplete_reasons)) != len(self.incomplete_reasons):
            raise ValueError("source-core incomplete reasons must be unique")

    @property
    def scan_canvas_state(self) -> EvidenceState:
        return (
            EvidenceState.SUPPORTED
            if self.lanes
            else EvidenceState.UNAVAILABLE
        )

    @property
    def content_state(self) -> EvidenceState:
        return (
            EvidenceState.SUPPORTED
            if self.lanes
            and all(
                lane.content.state == EvidenceState.SUPPORTED
                for lane in self.lanes
            )
            else EvidenceState.UNAVAILABLE
        )


def _content_fields(gray_work: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    intensity = gray_work.astype(np.float32, copy=False)
    intensity_content = intensity.copy()
    intensity_content[0, :] += intensity[0, :]
    intensity_content[1:, :] += intensity[:-1, :]
    intensity_content[-1, :] += intensity[-1, :]
    intensity_content[:-1, :] += intensity[1:, :]
    intensity_content[:, 0] += intensity[:, 0]
    intensity_content[:, 1:] += intensity[:, :-1]
    intensity_content[:, -1] += intensity[:, -1]
    intensity_content[:, :-1] += intensity[:, 1:]
    intensity_content *= np.float32(0.2)
    np.subtract(intensity, intensity_content, out=intensity_content)
    np.abs(intensity_content, out=intensity_content)
    intensity_content /= np.float32(255.0)

    texture_content = np.zeros_like(intensity)
    np.subtract(
        intensity[:, 1:],
        intensity[:, :-1],
        out=texture_content[:, 1:],
    )
    np.abs(texture_content[:, 1:], out=texture_content[:, 1:])
    row_block = max(1, min(128, intensity.shape[0] - 1))
    for start in range(1, intensity.shape[0], row_block):
        stop = min(intensity.shape[0], start + row_block)
        vertical = np.empty(
            (stop - start, intensity.shape[1]),
            dtype=np.float32,
        )
        np.subtract(
            intensity[start:stop, :],
            intensity[start - 1 : stop - 1, :],
            out=vertical,
        )
        np.abs(vertical, out=vertical)
        texture_content[start:stop, :] += vertical
    texture_content /= np.float32(510.0)
    return intensity_content, texture_content


def _empty_run_table() -> ContentRowRunTable:
    arrays = tuple(np.empty(0, dtype=np.int32) for _ in range(4))
    for array in arrays:
        array.flags.writeable = False
    return ContentRowRunTable(*arrays)


def _content_field_blocks(
    gray: np.ndarray,
    maximum_block_pixels: int,
):
    if gray.ndim != 2 or min(gray.shape) <= 0 or maximum_block_pixels <= 0:
        raise ValueError("content field streaming requires a bounded gray image")
    block_rows = max(1, maximum_block_pixels // gray.shape[1])
    for start in range(0, gray.shape[0], block_rows):
        stop = min(gray.shape[0], start + block_rows)
        halo_start = max(0, start - 1)
        halo_stop = min(gray.shape[0], stop + 1)
        intensity, texture = _content_fields(
            gray[halo_start:halo_stop]
        )
        local_start = start - halo_start
        local_stop = local_start + stop - start
        yield (
            start,
            stop,
            intensity[local_start:local_stop],
            texture[local_start:local_stop],
        )


def _streaming_content_thresholds(
    gray: np.ndarray,
    *,
    percentile: float,
    minimum_range: float,
    maximum_percentile_samples: int,
    maximum_block_pixels: int,
) -> tuple[float | None, float | None, float, float, int]:
    sample_step = max(
        1,
        int(
            np.ceil(
                gray.size / float(maximum_percentile_samples)
            )
        ),
    )
    intensity_samples: list[np.ndarray] = []
    texture_samples: list[np.ndarray] = []
    intensity_minimum = float("inf")
    intensity_maximum = float("-inf")
    texture_minimum = float("inf")
    texture_maximum = float("-inf")
    peak_bytes = 0
    block_count = 0
    width = gray.shape[1]
    for start, stop, intensity, texture in _content_field_blocks(
        gray,
        maximum_block_pixels,
    ):
        block_count += 1
        intensity_minimum = min(
            intensity_minimum,
            float(intensity.min()),
        )
        intensity_maximum = max(
            intensity_maximum,
            float(intensity.max()),
        )
        texture_minimum = min(
            texture_minimum,
            float(texture.min()),
        )
        texture_maximum = max(
            texture_maximum,
            float(texture.max()),
        )
        global_start = start * width
        first_global = (
            (global_start + sample_step - 1) // sample_step
        ) * sample_step
        local_start = first_global - global_start
        intensity_samples.append(
            intensity.reshape(-1)[local_start::sample_step].copy()
        )
        texture_samples.append(
            texture.reshape(-1)[local_start::sample_step].copy()
        )
        peak_bytes = max(
            peak_bytes,
            intensity.nbytes + texture.nbytes,
        )
    intensity_sample = np.concatenate(intensity_samples)
    texture_sample = np.concatenate(texture_samples)
    peak_bytes = max(
        peak_bytes,
        intensity_sample.nbytes + texture_sample.nbytes,
    )
    intensity_threshold = (
        None
        if intensity_maximum - intensity_minimum <= minimum_range
        else float(np.percentile(intensity_sample, percentile))
    )
    texture_threshold = (
        None
        if texture_maximum - texture_minimum <= minimum_range
        else float(np.percentile(texture_sample, percentile))
    )
    return (
        intensity_threshold,
        texture_threshold,
        intensity_minimum,
        texture_minimum,
        peak_bytes,
    )


def _streaming_content_activation_masks(
    gray: np.ndarray,
    *,
    intensity_threshold: float,
    texture_threshold: float,
    intensity_minimum: float,
    texture_minimum: float,
    minimum_active_pixels: int,
    maximum_block_pixels: int,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    intensity_mask = np.empty(gray.shape, dtype=np.bool_)
    texture_mask = np.empty(gray.shape, dtype=np.bool_)
    peak_block_bytes = 0
    for start, stop, intensity, texture in _content_field_blocks(
        gray,
        maximum_block_pixels,
    ):
        intensity_mask[start:stop] = (
            intensity > intensity_threshold
            if intensity_threshold <= intensity_minimum
            else intensity >= intensity_threshold
        )
        texture_mask[start:stop] = (
            texture > texture_threshold
            if texture_threshold <= texture_minimum
            else texture >= texture_threshold
        )
        peak_block_bytes = max(
            peak_block_bytes,
            intensity.nbytes + texture.nbytes,
        )

    axis_support = int(np.ceil(np.sqrt(minimum_active_pixels)))
    for mask in (intensity_mask, texture_mask):
        if int(np.count_nonzero(mask)) < minimum_active_pixels:
            mask.fill(False)
            continue
        supported_rows = np.count_nonzero(mask, axis=1) >= axis_support
        supported_columns = (
            np.count_nonzero(mask, axis=0) >= axis_support
        )
        mask &= supported_rows[:, None]
        mask &= supported_columns[None, :]
        if int(np.count_nonzero(mask)) < minimum_active_pixels:
            mask.fill(False)
    return (
        intensity_mask,
        texture_mask,
        peak_block_bytes,
        int(
            np.ceil(
                gray.shape[0]
                / max(1, maximum_block_pixels // gray.shape[1])
            )
        ),
    )


def _four_connected_run_components(
    positive_mask: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    int,
]:
    """Label strict 4-connected row runs with a vectorized overlap graph."""
    maximum_block_pixels = 1_048_576
    block_rows = max(
        1,
        maximum_block_pixels // positive_mask.shape[1],
    )
    row_chunks: list[np.ndarray] = []
    left_chunks: list[np.ndarray] = []
    right_chunks: list[np.ndarray] = []
    extraction_peak_bytes = 0
    for start in range(0, positive_mask.shape[0], block_rows):
        stop = min(positive_mask.shape[0], start + block_rows)
        block = positive_mask[start:stop]
        starts = block.copy()
        starts[:, 1:] &= ~block[:, :-1]
        ends = block.copy()
        ends[:, :-1] &= ~block[:, 1:]
        start_rows, start_columns = np.nonzero(starts)
        end_rows, end_columns = np.nonzero(ends)
        if (
            start_rows.size != end_rows.size
            or not np.array_equal(start_rows, end_rows)
        ):
            raise RuntimeError("content RLE extraction lost row identity")
        row_chunks.append(
            (start_rows + start).astype(np.int32, copy=False)
        )
        left_chunks.append(start_columns.astype(np.int32, copy=False))
        right_chunks.append(
            (end_columns + 1).astype(np.int32, copy=False)
        )
        extraction_peak_bytes = max(
            extraction_peak_bytes,
            sum(
                item.nbytes
                for item in (
                    starts,
                    ends,
                    start_rows,
                    start_columns,
                    end_rows,
                    end_columns,
                )
            ),
        )
    if row_chunks:
        extraction_chunk_bytes = sum(
            item.nbytes
            for item in (*row_chunks, *left_chunks, *right_chunks)
        )
        run_rows = np.concatenate(row_chunks)
        run_lefts = np.concatenate(left_chunks)
        run_rights = np.concatenate(right_chunks)
    else:
        extraction_chunk_bytes = 0
        run_rows = np.empty(0, dtype=np.int32)
        run_lefts = np.empty(0, dtype=np.int32)
        run_rights = np.empty(0, dtype=np.int32)
    row_chunks.clear()
    left_chunks.clear()
    right_chunks.clear()
    run_count = int(run_rows.size)
    if run_count == 0:
        empty = np.empty(0, dtype=np.int32)
        return (
            empty,
            empty.copy(),
            empty.copy(),
            empty.copy(),
            np.empty(0, dtype=np.int64),
            extraction_peak_bytes,
        )

    row_counts = np.bincount(
        run_rows,
        minlength=positive_mask.shape[0],
    ).astype(np.int64, copy=False)
    row_offsets = np.empty(row_counts.size + 1, dtype=np.int64)
    row_offsets[0] = 0
    np.cumsum(row_counts, out=row_offsets[1:])

    previous_edge_chunks: list[np.ndarray] = []
    current_edge_chunks: list[np.ndarray] = []
    for row in range(1, positive_mask.shape[0]):
        previous_start = int(row_offsets[row - 1])
        previous_stop = int(row_offsets[row])
        current_start = previous_stop
        current_stop = int(row_offsets[row + 1])
        if previous_start == previous_stop or current_start == current_stop:
            continue
        previous_lefts = run_lefts[previous_start:previous_stop]
        previous_rights = run_rights[previous_start:previous_stop]
        current_lefts = run_lefts[current_start:current_stop]
        current_rights = run_rights[current_start:current_stop]
        first_overlaps = np.searchsorted(
            previous_rights,
            current_lefts,
            side="right",
        )
        overlap_stops = np.searchsorted(
            previous_lefts,
            current_rights,
            side="left",
        )
        overlap_counts = overlap_stops - first_overlaps
        connected = overlap_counts > 0
        if not np.any(connected):
            continue
        overlap_counts = overlap_counts[connected]
        first_overlaps = first_overlaps[connected]
        current_indices = np.arange(
            current_start,
            current_stop,
            dtype=np.int32,
        )[connected]
        group_starts = np.cumsum(overlap_counts, dtype=np.int64)
        group_starts -= overlap_counts
        edge_count = int(np.sum(overlap_counts, dtype=np.int64))
        edge_positions = np.arange(edge_count, dtype=np.int32)
        previous_bases = (
            previous_start
            + first_overlaps.astype(np.int64, copy=False)
            - group_starts
        ).astype(np.int32)
        previous_edge_chunks.append(
            edge_positions
            + np.repeat(previous_bases, overlap_counts),
        )
        current_edge_chunks.append(
            np.repeat(current_indices, overlap_counts),
        )

    if previous_edge_chunks:
        edge_chunk_bytes = sum(
            item.nbytes
            for item in (*previous_edge_chunks, *current_edge_chunks)
        )
        previous_edges = np.concatenate(previous_edge_chunks)
        current_edges = np.concatenate(current_edge_chunks)
        previous_edge_chunks.clear()
        current_edge_chunks.clear()
    else:
        edge_chunk_bytes = 0
        previous_edges = np.empty(0, dtype=np.int32)
        current_edges = np.empty(0, dtype=np.int32)

    parents = np.arange(run_count, dtype=np.int32)
    while previous_edges.size:
        while True:
            grandparents = parents[parents]
            if np.array_equal(grandparents, parents):
                break
            parents[:] = grandparents
        previous_roots = parents[previous_edges]
        current_roots = parents[current_edges]
        higher_roots = np.maximum(previous_roots, current_roots)
        lower_roots = np.minimum(previous_roots, current_roots)
        if not np.any(lower_roots < parents[higher_roots]):
            break
        np.minimum.at(parents, higher_roots, lower_roots)

    while True:
        roots = parents[parents]
        if np.array_equal(roots, parents):
            break
        parents[:] = roots
    roots = parents
    unique_roots, run_components = np.unique(
        roots,
        return_inverse=True,
    )
    run_components = run_components.astype(np.int32, copy=False)
    component_cells = np.zeros(unique_roots.size, dtype=np.int64)
    run_lengths = run_rights.astype(np.int64) - run_lefts
    np.add.at(component_cells, run_components, run_lengths)
    work_bytes = sum(
        item.nbytes
        for item in (
            run_rows,
            run_lefts,
            run_rights,
            parents,
            row_counts,
            row_offsets,
            previous_edges,
            current_edges,
            unique_roots,
            run_components,
            run_lengths,
            component_cells,
        )
    ) + max(
        extraction_peak_bytes + extraction_chunk_bytes,
        edge_chunk_bytes,
    )
    return (
        run_rows,
        run_lefts,
        run_rights,
        run_components,
        component_cells,
        work_bytes,
    )


def _compact_components(
    positive_mask: np.ndarray,
    domain: SourceStripValidationDomain,
    minimum_active_pixels: int,
    provenance: MeasurementProvenance,
) -> tuple[
    tuple[SourceContentComponent, ...],
    ContentRowRunTable,
    int,
    int,
]:
    box = domain.work_box
    if (
        positive_mask.dtype != np.bool_
        or positive_mask.ndim != 2
        or positive_mask.shape != (box.height, box.width)
    ):
        raise ValueError("content component mask must match the lane domain")
    (
        local_run_rows,
        local_run_lefts,
        local_run_rights,
        raw_run_components,
        component_cells,
        run_stage_bytes,
    ) = _four_connected_run_components(
        positive_mask,
    )
    raw_component_count = int(component_cells.size)
    keep = component_cells >= int(minimum_active_pixels)
    kept_components = np.flatnonzero(keep).astype(np.int32)
    if not kept_components.size:
        peak_bytes = (
            run_stage_bytes
            + keep.nbytes
            + kept_components.nbytes
        )
        return (), _empty_run_table(), int(raw_component_count), peak_bytes

    component_map = np.full(component_cells.size, -1, dtype=np.int32)
    component_map[kept_components] = np.arange(
        kept_components.size,
        dtype=np.int32,
    )
    kept_runs = keep[raw_run_components]
    run_components = component_map[raw_run_components[kept_runs]]
    run_rows = (local_run_rows[kept_runs] + box.top).astype(
        np.int32,
        copy=False,
    )
    run_lefts = (local_run_lefts[kept_runs] + box.left).astype(
        np.int32,
        copy=False,
    )
    run_rights = (local_run_rights[kept_runs] + box.left).astype(
        np.int32,
        copy=False,
    )
    order = np.argsort(run_components, kind="stable")
    run_components = run_components[order].astype(np.int32, copy=False)
    run_rows = run_rows[order]
    run_lefts = run_lefts[order]
    run_rights = run_rights[order]

    run_counts = np.bincount(
        run_components,
        minlength=kept_components.size,
    ).astype(np.int64)
    offsets = np.concatenate(
        (np.zeros(1, dtype=np.int64), np.cumsum(run_counts[:-1]))
    )
    minimum_rows = np.full(
        kept_components.size,
        np.iinfo(np.int32).max,
        np.int32,
    )
    maximum_rows = np.full(kept_components.size, -1, np.int32)
    minimum_lefts = np.full(
        kept_components.size,
        np.iinfo(np.int32).max,
        np.int32,
    )
    maximum_rights = np.full(kept_components.size, -1, np.int32)
    np.minimum.at(minimum_rows, run_components, run_rows)
    np.maximum.at(maximum_rows, run_components, run_rows)
    np.minimum.at(minimum_lefts, run_components, run_lefts)
    np.maximum.at(maximum_rights, run_components, run_rights)

    for array in (run_rows, run_lefts, run_rights, run_components):
        array.flags.writeable = False
    table = ContentRowRunTable(
        rows=run_rows,
        lefts=run_lefts,
        rights=run_rights,
        component_indices=run_components,
    )
    components: list[SourceContentComponent] = []
    for component_index, raw_component in enumerate(kept_components):
        footprint = Box(
            int(minimum_lefts[component_index]),
            int(minimum_rows[component_index]),
            int(maximum_rights[component_index]),
            int(maximum_rows[component_index]) + 1,
        )
        cells = int(component_cells[int(raw_component)])
        components.append(
            SourceContentComponent(
                component_id=(
                    f"{domain.lane_id}:content:{component_index:06d}"
                ),
                row_run_offset=int(offsets[component_index]),
                row_run_count=int(run_counts[component_index]),
                footprint=footprint,
                positive_cells=cells,
                censored=(
                    footprint.left == box.left
                    or footprint.right == box.right
                    or footprint.top == box.top
                    or footprint.bottom == box.bottom
                ),
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.SOURCE_CONTENT,
                    observation_id=ObservationId(
                        f"{domain.lane_id}:content:{component_index:06d}"
                    ),
                    dependencies=provenance.dependencies,
                    description=(
                        "strict four-connected spatially supported content"
                    ),
                ),
            )
        )
    peak_bytes = sum(
        item.nbytes
        for item in (
            keep,
            kept_components,
            component_map,
            kept_runs,
            run_components,
            order,
            run_rows,
            run_lefts,
            run_rights,
            run_counts,
            offsets,
            minimum_rows,
            maximum_rows,
            minimum_lefts,
            maximum_rights,
        )
    ) + run_stage_bytes
    return (
        tuple(components),
        table,
        int(raw_component_count),
        peak_bytes,
    )


def observe_source_content(
    gray_work: np.ndarray,
    domain: SourceStripValidationDomain,
    configuration: ContentConfiguration,
) -> SourceContentObservation:
    started = perf_counter()
    box = domain.work_box
    if (
        gray_work.ndim != 2
        or box.left < 0
        or box.top < 0
        or box.right > gray_work.shape[1]
        or box.bottom > gray_work.shape[0]
    ):
        raise ValueError("source content domain exceeds the work image")
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.SOURCE_CONTENT,
        observation_id=ObservationId(f"source_content:{domain.lane_id}"),
        dependencies=(
            MeasurementIdentity.BASE_GRAY,
            MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
            MeasurementIdentity.SCAN_CANVAS_GEOMETRY,
        ),
        description="immutable source-coordinate positive content components",
    )
    view = gray_work[box.top : box.bottom, box.left : box.right]
    parameters = configuration.evidence
    (
        intensity_threshold,
        texture_threshold,
        intensity_minimum,
        texture_minimum,
        threshold_peak_bytes,
    ) = _streaming_content_thresholds(
        view,
        percentile=parameters.activation_percentile,
        minimum_range=parameters.minimum_evidence_range,
        maximum_percentile_samples=(
            parameters.maximum_percentile_samples
        ),
        maximum_block_pixels=(
            parameters.maximum_streaming_block_pixels
        ),
    )
    if intensity_threshold is None or texture_threshold is None:
        statistics = SourceContentMeasurementStatistics(
            domain_pixels=int(view.size),
            streaming_block_count=int(
                np.ceil(
                    view.shape[0]
                    / max(
                        1,
                        parameters.maximum_streaming_block_pixels
                        // view.shape[1],
                    )
                )
            ),
            intensity_active_cells=0,
            texture_active_cells=0,
            positive_cells=0,
            run_count=0,
            raw_component_count=0,
            component_count=0,
            censored_component_count=0,
            deterministic_seconds=perf_counter() - started,
            peak_temporary_bytes=threshold_peak_bytes,
        )
        return SourceContentObservation(
            lane_id=domain.lane_id,
            state=EvidenceState.UNAVAILABLE,
            intensity_threshold=None,
            texture_threshold=None,
            components=(),
            row_run_table=_empty_run_table(),
            statistics=statistics,
            provenance=provenance,
        )

    (
        intensity_mask,
        texture_mask,
        activation_block_peak_bytes,
        streaming_block_count,
    ) = _streaming_content_activation_masks(
        view,
        intensity_threshold=intensity_threshold,
        texture_threshold=texture_threshold,
        intensity_minimum=intensity_minimum,
        texture_minimum=texture_minimum,
        minimum_active_pixels=parameters.minimum_active_pixels,
        maximum_block_pixels=(
            parameters.maximum_streaming_block_pixels
        ),
    )
    positive_mask = intensity_mask & texture_mask
    intensity_active_cells = int(np.count_nonzero(intensity_mask))
    texture_active_cells = int(np.count_nonzero(texture_mask))
    positive_cells = int(np.count_nonzero(positive_mask))
    field_stage_peak = (
        intensity_mask.nbytes
        + texture_mask.nbytes
        + positive_mask.nbytes
        + activation_block_peak_bytes
    )
    del intensity_mask, texture_mask
    (
        components,
        run_table,
        raw_component_count,
        component_stage_bytes,
    ) = _compact_components(
        positive_mask,
        domain,
        parameters.minimum_active_pixels,
        provenance,
    )
    peak_bytes = max(
        threshold_peak_bytes,
        field_stage_peak,
        positive_mask.nbytes + component_stage_bytes,
    )
    statistics = SourceContentMeasurementStatistics(
        domain_pixels=int(view.size),
        streaming_block_count=streaming_block_count * 2,
        intensity_active_cells=intensity_active_cells,
        texture_active_cells=texture_active_cells,
        positive_cells=positive_cells,
        run_count=run_table.run_count,
        raw_component_count=raw_component_count,
        component_count=len(components),
        censored_component_count=sum(
            int(component.censored) for component in components
        ),
        deterministic_seconds=perf_counter() - started,
        peak_temporary_bytes=peak_bytes,
    )
    return SourceContentObservation(
        lane_id=domain.lane_id,
        state=EvidenceState.SUPPORTED,
        intensity_threshold=float(intensity_threshold),
        texture_threshold=float(texture_threshold),
        components=components,
        row_run_table=run_table,
        statistics=statistics,
        provenance=provenance,
    )
