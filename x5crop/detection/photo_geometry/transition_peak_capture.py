"""Bounded group capture from already measured, candidate-independent traces."""

from dataclasses import dataclass, field, replace

from .transition_peak_source import TransitionPeakGroupSource


@dataclass
class TransitionPeakCapture:
    maximum_bytes: int
    complete: bool = field(default=True, init=False)
    groups: dict[str, TransitionPeakGroupSource] = field(default_factory=dict, init=False)
    reserved_bytes: int = field(default=1024, init=False)
    peak_temporary_bytes: int = field(default=1024, init=False)
    value_visit_bound: int = field(default=0, init=False)
    attempted: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if type(self.maximum_bytes) is not int or self.maximum_bytes < 0:
            raise ValueError("peak source capture requires its original memory bound")
        if self.maximum_bytes < self.reserved_bytes:
            self.complete = False

    def reserve_group(self, group_coordinates: int, reliable_coordinates: int, candidates: int) -> bool:
        if not self.complete:
            return False
        self.attempted = True
        self.value_visit_bound += 32 + 8 * (group_coordinates + reliable_coordinates + candidates)
        # Retain the group once and reserve every candidate reference, including
        # a transient reference later rejected by ownership or fitting.
        required = 2048 + 256 * (reliable_coordinates + candidates) + 512 * candidates
        if self.reserved_bytes + required > self.maximum_bytes:
            self.complete = False
            self.groups.clear()
            return False
        self.reserved_bytes += required
        self.peak_temporary_bytes = max(self.peak_temporary_bytes, self.reserved_bytes)
        return True

    def retain(self, group: TransitionPeakGroupSource) -> None:
        if self.complete:
            previous = self.groups.setdefault(group.primitive_id, group)
            if previous != group:
                raise ValueError("one query changed a complete original peak group")


def peak_source_receipt(transitions, receipt, trace_sources, capture):
    """Charge retained provenance and all attempted group work, even on failure."""
    sources = tuple(trace_sources)
    failed = capture is not None and not capture.complete
    groups = () if capture is None or failed else tuple(capture.groups.values())
    if failed:
        transitions = tuple(replace(item, peak_source=None) for item in transitions)
    references = tuple(item.peak_source for item in transitions if item.peak_source is not None)
    retained = (sum(source.retained_bytes for source in sources)
                + sum(group.retained_bytes for group in groups)
                + sum(reference.retained_bytes for reference in references))
    # Disjoint groups, reliable coordinates and candidates are each bounded
    # by Q. Capture costs at most 64Q; reserve four such passes for capture,
    # typed query/replacement checks and final source-context validation.
    visit_bound = (sum(source.signal_value_visit_count + 32 for source in sources)
                   + (0 if capture is None else 32 + (256 * receipt.registered_coordinate_count if capture.attempted else 0)))
    peak = max(retained, sum(source.retained_bytes for source in sources)
               + (0 if capture is None else capture.peak_temporary_bytes))
    return transitions, replace(receipt,
        peak_temporary_bytes=receipt.peak_temporary_bytes + peak,
        peak_source_value_visit_bound=visit_bound,
        peak_source_group_count=len(groups), peak_source_reference_count=len(references),
        peak_source_retained_bytes=retained, peak_source_bound_exceeded=failed,
        peak_source_capture_attempted=capture is not None and capture.attempted), sources, groups
