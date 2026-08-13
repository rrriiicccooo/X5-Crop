from __future__ import annotations

import inspect
from types import SimpleNamespace
import unittest

from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from x5crop.configuration.model import HolderLayoutAuthority
from x5crop.formats import FRAME_DIMENSION_TOLERANCE_SPEC, FramePhysicalSpec
from x5crop.detection.photo_geometry.chain_authority import (
    placement_local_advance_authorized,
)
from x5crop.detection.photo_geometry.sequence_models import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    SequenceDiscoveryKind,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    BasicAxisProfile,
    OrdinalBoundaryRole,
    ProfileRun,
    SeparatorBandRoleProposal,
    SequenceRoleProposal,
)
from x5crop.detection.photo_geometry.sequence_separator_seeds import (
    direct_separator_groups,
)
from x5crop.detection.photo_geometry.sequence_seed import (
    visible_normal_phase_authority,
)
from x5crop.detection.photo_geometry.sequence_role_proposals import (
    build_sequence_role_proposals,
    role_canonical_relative,
    role_relative_projection,
)
from x5crop.detection.photo_geometry.sequence_grouping import build_sequence_groups
from x5crop.detection.photo_geometry.chain_records import complete_chain_record
from x5crop.detection.photo_geometry.detector import reconstruct_photo_geometry
from x5crop.detection.photo_geometry.selected_source_output import (
    resolve_selected_source_output,
)
from x5crop.detection.photo_geometry.local_advance import (
    local_advance_delta_from_observed_gap,
    merge_local_advance_relations,
)
from x5crop.detection.photo_geometry.edge_family_identity import (
    disjoint_family_pairs,
)
from x5crop.detection.photo_geometry.holder_layout_authority import (
    long_axis_fill_authority,
)
from x5crop.detection.photo_geometry.source_chain_materialization import (
    materialize_lane_placements,
    materialize_source_placements,
)
from x5crop.detection.photo_geometry.cross_placement import (
    materialize_cross_placement,
)
from x5crop.detection.photo_geometry.joint_axis_geometry import (
    JointAxisGeometry,
)
from x5crop.detection.photo_geometry.lane_gap_model import LaneGapModel
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry


def make_width_state() -> JointAxisGeometry:
    return JointAxisGeometry.create(
        axis_name="width",
        design_extent_mm=36.0,
        scale_interval_px_per_mm=PositiveInterval(10.0, 10.0),
        factor_interval=PositiveInterval(1.0, 1.0),
    )


def make_edge(ordinal: int, position: float, name: str):
    return (
        ordinal,
        FiniteInterval.exact(position),
        (ObservationId(name),),
    )



# Physical-chain contracts share small typed fixtures.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
