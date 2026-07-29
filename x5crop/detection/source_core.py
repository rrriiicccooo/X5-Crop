from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
from ..formats import FormatSpec
from ..image.evidence import (
    adaptive_activation_threshold,
    spatially_supported_activation_mask,
)
from .evidence.scan_canvas import (
    CanvasAxisScaleIntervals,
    ScanCanvasEvidence,
    ScanCanvasOutcome,
)


class FrameGridOutcome(str, Enum):
    NO_INDEPENDENT_PHASE_AUTHORITY = "no_independent_phase_authority"


class PhotoContainmentOutcome(str, Enum):
    NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE = (
        "not_applicable_frame_grid_unavailable"
    )


class VisualDeskewOutcome(str, Enum):
    NOT_APPLICABLE_CORE_UNAVAILABLE = "not_applicable_core_unavailable"


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
class FrameGridEvidence:
    outcome: FrameGridOutcome
    authority: None = None
    frame_slots: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome != FrameGridOutcome.NO_INDEPENDENT_PHASE_AUTHORITY:
            raise ValueError("current runtime has no other Grid outcome")
        if self.authority is not None or self.frame_slots:
            raise ValueError("unavailable Grid cannot carry authority or slots")

    @property
    def state(self) -> EvidenceState:
        return EvidenceState.UNAVAILABLE


@dataclass(frozen=True)
class PhotoContainmentEvidence:
    outcome: PhotoContainmentOutcome
    frame_envelopes: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.outcome
            != PhotoContainmentOutcome.NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE
            or self.frame_envelopes
        ):
            raise ValueError("current containment must be explicitly not applicable")

    @property
    def state(self) -> EvidenceState:
        return EvidenceState.NOT_APPLICABLE


@dataclass(frozen=True)
class OutputProtectionAuthority:
    format_id: str
    long_axis_mm: float
    short_axis_mm: float
    applied: bool = False

    def __post_init__(self) -> None:
        if (
            not self.format_id
            or self.long_axis_mm <= 0.0
            or self.short_axis_mm <= 0.0
        ):
            raise ValueError("output protection requires positive millimetre values")
        if self.applied:
            raise ValueError("protection cannot be applied without frame geometry")


@dataclass(frozen=True)
class SourceLaneEvidence:
    domain: SourceStripValidationDomain
    scan_canvas: ScanCanvasEvidence
    scales: CanvasAxisScaleIntervals
    content: SourceContentObservation

    def __post_init__(self) -> None:
        if self.scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED:
            raise ValueError("source lane requires unique scan-canvas authority")
        if self.scan_canvas.axis_scales != self.scales:
            raise ValueError("source lane scale owner must be scan-canvas evidence")
        if self.domain.lane_id != self.content.lane_id:
            raise ValueError("source lane content must share the lane identity")


@dataclass(frozen=True)
class SourceCoreEvidence:
    lanes: tuple[SourceLaneEvidence, ...]
    scan_canvas_state: EvidenceState
    content_state: EvidenceState
    grid: FrameGridEvidence
    containment: PhotoContainmentEvidence
    protection_authority: OutputProtectionAuthority
    visual_deskew_outcome: VisualDeskewOutcome
    incomplete_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(set(lane.domain.lane_id for lane in self.lanes)) != len(self.lanes):
            raise ValueError("source-core lane identities must be unique")
        if self.grid.state != EvidenceState.UNAVAILABLE:
            raise ValueError("current source core cannot carry frame Grid authority")
        if self.containment.state != EvidenceState.NOT_APPLICABLE:
            raise ValueError("current containment must follow unavailable Grid")
        if (
            self.visual_deskew_outcome
            != VisualDeskewOutcome.NOT_APPLICABLE_CORE_UNAVAILABLE
        ):
            raise ValueError("current visual deskew must be not applicable")
        if len(set(self.incomplete_reasons)) != len(self.incomplete_reasons):
            raise ValueError("source-core incomplete reasons must be unique")
        lanes_supported = bool(self.lanes)
        if (
            self.scan_canvas_state == EvidenceState.SUPPORTED
        ) != lanes_supported:
            raise ValueError("scan-canvas state must match available lanes")
        content_supported = lanes_supported and all(
            lane.content.state == EvidenceState.SUPPORTED
            for lane in self.lanes
        )
        if (
            self.content_state == EvidenceState.SUPPORTED
        ) != content_supported:
            raise ValueError("content state must match lane observations")


_PROTECTION_MM = {
    "half": (0.15, 0.25),
    "135": (0.25, 0.25),
    "135-dual": (0.25, 0.25),
    "120-645": (0.30, 0.25),
    "120-66": (0.40, 0.25),
    "xpan": (0.45, 0.25),
    "120-67": (0.50, 0.25),
}


def output_protection_authority(spec: FormatSpec) -> OutputProtectionAuthority:
    long_mm, short_mm = _PROTECTION_MM[spec.format_id]
    return OutputProtectionAuthority(spec.format_id, long_mm, short_mm)


def unavailable_frame_grid() -> FrameGridEvidence:
    return FrameGridEvidence(
        outcome=FrameGridOutcome.NO_INDEPENDENT_PHASE_AUTHORITY,
        authority=None,
        frame_slots=(),
    )


def unavailable_photo_containment() -> PhotoContainmentEvidence:
    return PhotoContainmentEvidence(
        outcome=PhotoContainmentOutcome.NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE,
        frame_envelopes=(),
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
    starts_mask = positive_mask.copy()
    starts_mask[:, 1:] &= ~positive_mask[:, :-1]
    ends_mask = positive_mask.copy()
    ends_mask[:, :-1] &= ~positive_mask[:, 1:]
    start_rows, start_columns = np.nonzero(starts_mask)
    end_rows, end_columns = np.nonzero(ends_mask)
    if (
        start_rows.size != end_rows.size
        or not np.array_equal(start_rows, end_rows)
    ):
        raise RuntimeError("content RLE extraction lost row identity")

    run_rows = start_rows.astype(np.int32, copy=False)
    run_lefts = start_columns.astype(np.int32, copy=False)
    run_rights = (end_columns + 1).astype(np.int32, copy=False)
    run_count = int(run_rows.size)
    if run_count == 0:
        empty = np.empty(0, dtype=np.int32)
        return (
            empty,
            empty.copy(),
            empty.copy(),
            empty.copy(),
            np.empty(0, dtype=np.int64),
            sum(
                item.nbytes
                for item in (
                    starts_mask,
                    ends_mask,
                    start_rows,
                    start_columns,
                    end_rows,
                    end_columns,
                )
            ),
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
            starts_mask,
            ends_mask,
            start_rows,
            start_columns,
            end_rows,
            end_columns,
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
    ) + edge_chunk_bytes
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
    intensity_field, texture_field = _content_fields(view)
    parameters = configuration.evidence
    intensity_threshold = adaptive_activation_threshold(
        intensity_field,
        parameters.activation_percentile,
        parameters.minimum_evidence_range,
        parameters.maximum_percentile_samples,
    )
    texture_threshold = adaptive_activation_threshold(
        texture_field,
        parameters.activation_percentile,
        parameters.minimum_evidence_range,
        parameters.maximum_percentile_samples,
    )
    if intensity_threshold is None or texture_threshold is None:
        statistics = SourceContentMeasurementStatistics(
            domain_pixels=int(view.size),
            intensity_active_cells=0,
            texture_active_cells=0,
            positive_cells=0,
            run_count=0,
            raw_component_count=0,
            component_count=0,
            censored_component_count=0,
            deterministic_seconds=perf_counter() - started,
            peak_temporary_bytes=(
                intensity_field.nbytes + texture_field.nbytes
            ),
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

    intensity_mask = spatially_supported_activation_mask(
        intensity_field,
        intensity_threshold,
        parameters.minimum_active_pixels,
    )
    texture_mask = spatially_supported_activation_mask(
        texture_field,
        texture_threshold,
        parameters.minimum_active_pixels,
    )
    positive_mask = intensity_mask & texture_mask
    intensity_active_cells = int(np.count_nonzero(intensity_mask))
    texture_active_cells = int(np.count_nonzero(texture_mask))
    positive_cells = int(np.count_nonzero(positive_mask))
    field_stage_peak = (
        intensity_field.nbytes
        + texture_field.nbytes
        + intensity_mask.nbytes
        + texture_mask.nbytes
        + positive_mask.nbytes
        + min(128, max(0, view.shape[0] - 1))
        * view.shape[1]
        * np.dtype(np.float32).itemsize
    )
    del intensity_field, texture_field, intensity_mask, texture_mask
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
        field_stage_peak,
        positive_mask.nbytes + component_stage_bytes,
    )
    statistics = SourceContentMeasurementStatistics(
        domain_pixels=int(view.size),
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
