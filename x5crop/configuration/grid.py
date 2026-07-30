from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from ..domain import FiniteInterval


GRID_ALGORITHM_REVISION = "bounded_ordered_capacity_grid_v5"
GRID_CONFIGURATION_REVISION = "safe_crop_prior_v1"


@dataclass(frozen=True)
class CalibrationCell:
    sample_id: str
    source_sha256: str
    format_id: str
    strip_mode: str
    aperture_long_axis_mm: float
    orientation: str
    count: int
    partial_placement: str
    interaction_class: str

    def __post_init__(self) -> None:
        if (
            not self.sample_id
            or len(self.source_sha256) != 64
            or not self.format_id
            or self.strip_mode not in {"full", "partial"}
            or self.aperture_long_axis_mm <= 0.0
            or self.orientation not in {"horizontal", "vertical"}
            or self.count <= 0
            or not self.partial_placement
            or not self.interaction_class
        ):
            raise ValueError("calibration cell is incomplete")


@dataclass(frozen=True)
class GridSearchContractReceipt:
    slot_count_policy: str
    placement_seed_limit_per_lane_component: int
    observed_candidate_limit_per_corridor: int
    total_candidate_limit_per_corridor: int
    proposal_resolution: str
    omission_resolution: str

    def __post_init__(self) -> None:
        if (
            self.slot_count_policy != "single_resolved_output_slot_count"
            or self.placement_seed_limit_per_lane_component != 6
            or self.observed_candidate_limit_per_corridor != 2
            or self.total_candidate_limit_per_corridor != 3
            or self.proposal_resolution
            != "output_equivalence_outward_union_only"
            or self.omission_resolution
            != "proven_equivalent_and_union_absorbed_only"
        ):
            raise ValueError("Grid search contract receipt is not canonical")


@dataclass(frozen=True)
class CalibrationReceipt:
    schema: str
    algorithm_revision: str
    configuration_revision: str
    provenance: str
    cells: tuple[CalibrationCell, ...]
    nominal_sample_count: int
    stress_sample_id: str
    coverage_measurement_record_count: int
    search_contract: GridSearchContractReceipt

    def __post_init__(self) -> None:
        if self.schema != "x5crop_grid_calibration_receipt_v2":
            raise ValueError("unsupported calibration receipt schema")
        if self.provenance != "user_confirmed_geometry":
            raise ValueError("calibration geometry provenance must remain explicit")
        if len({cell.source_sha256 for cell in self.cells}) != len(self.cells):
            raise ValueError("calibration receipt source SHA values must be unique")
        if (
            self.nominal_sample_count != len(self.cells)
            or self.stress_sample_id != "S098"
            or self.coverage_measurement_record_count != 102
        ):
            raise ValueError("calibration coverage receipt is inconsistent")

    @property
    def source_sha256_set(self) -> tuple[str, ...]:
        return tuple(sorted(cell.source_sha256 for cell in self.cells))

    @property
    def calibration_receipt_id(self) -> str:
        payload = json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + sha256(payload).hexdigest()


# The confirmed geometry calibrated only prior centres and conservative search
# intervals. It is deliberately not represented as runtime separator evidence.
GRID_CALIBRATION_RECEIPT = CalibrationReceipt(
    schema="x5crop_grid_calibration_receipt_v2",
    algorithm_revision=GRID_ALGORITHM_REVISION,
    configuration_revision=GRID_CONFIGURATION_REVISION,
    provenance="user_confirmed_geometry",
    cells=(
        CalibrationCell(
            "S027",
            "e92bbf94bf1d2b1334d00c83bc7dc69766a41dee063e8b2f1961e292595d0dac",
            "135",
            "full",
            36.0,
            "horizontal",
            6,
            "full",
            "separated",
        ),
        CalibrationCell(
            "S035",
            "f46a2c7c6aec700e7d068b456cb1e1fb92939438c47cbc934d5e6adeb7655f5d",
            "135",
            "full",
            36.0,
            "horizontal",
            6,
            "full",
            "separated",
        ),
        CalibrationCell(
            "S051",
            "5c2b7275a3fb037359b0cea50306187ea9084a88e0a3d849eb44a6d57b4f0a23",
            "135",
            "partial",
            36.0,
            "horizontal",
            3,
            "leading",
            "separated",
        ),
        CalibrationCell(
            "S055",
            "5a4a786f6a2ba75bc894d6263e6527ac2169a5be4d6bddb0ea8c45f10f23a181",
            "135",
            "partial",
            36.0,
            "horizontal",
            4,
            "leading",
            "one_sided",
        ),
        CalibrationCell(
            "S062",
            "ed1e0aba8b78a8619ffe0cc14b855fdd87ebcc92f4c8c137da3fef8f7192a7f6",
            "120-66",
            "partial",
            54.0,
            "vertical",
            3,
            "trailing",
            "blank_and_separated",
        ),
        CalibrationCell(
            "S091",
            "d3339937812d4e645736d5bb109d2516ca2c43e146a7168d4e5402ca1f967d67",
            "120-66",
            "partial",
            54.0,
            "vertical",
            3,
            "trailing",
            "separated",
        ),
        CalibrationCell(
            "S094",
            "6f615e3519266a5474294c4de2d85e13a5e4dab7793cf9d1b356b519e6309233",
            "120-67",
            "full",
            70.0,
            "horizontal",
            3,
            "full",
            "separated",
        ),
        CalibrationCell(
            "S109",
            "460d0664de16d9d41ccf2a0bb06cd32c52639b56f20efce5e4be73f74ee5012c",
            "half",
            "partial",
            18.0,
            "horizontal",
            7,
            "trailing",
            "contact_and_separated",
        ),
    ),
    nominal_sample_count=8,
    stress_sample_id="S098",
    coverage_measurement_record_count=102,
    search_contract=GridSearchContractReceipt(
        slot_count_policy="single_resolved_output_slot_count",
        placement_seed_limit_per_lane_component=6,
        observed_candidate_limit_per_corridor=2,
        total_candidate_limit_per_corridor=3,
        proposal_resolution="output_equivalence_outward_union_only",
        omission_resolution="proven_equivalent_and_union_absorbed_only",
    ),
)

CALIBRATION_RECEIPT_ID = GRID_CALIBRATION_RECEIPT.calibration_receipt_id


@dataclass(frozen=True)
class FrameGridSearchPrior:
    format_id: str
    strip_mode: str
    aperture_long_axis_mm: float
    pitch_mm: FiniteInterval
    gutter_mm: FiniteInterval
    full_leading_margin_mm: FiniteInterval
    full_trailing_margin_mm: FiniteInterval
    boundary_uncertainty_mm: float
    equality_interval_mm: float
    calibration_receipt_id: str
    provenance: str

    def __post_init__(self) -> None:
        if (
            not self.format_id
            or self.strip_mode not in {"full", "partial"}
            or self.aperture_long_axis_mm <= 0.0
            or self.boundary_uncertainty_mm <= 0.0
            or self.equality_interval_mm <= 0.0
            or self.calibration_receipt_id != CALIBRATION_RECEIPT_ID
            or self.provenance not in {
                "user_confirmed_geometry",
                "physical_rule",
            }
        ):
            raise ValueError("frame-grid search prior is incomplete")
        if not self.pitch_mm.contains(
            self.aperture_long_axis_mm + self.gutter_mm.center,
            epsilon=self.equality_interval_mm,
        ):
            raise ValueError("pitch and gutter prior centres disagree")


_PRIOR_RANGES: dict[str, tuple[FiniteInterval, FiniteInterval, FiniteInterval]] = {
    "135": (
        FiniteInterval(37.0, 39.0),
        FiniteInterval(1.0, 3.0),
        FiniteInterval(2.0, 5.0),
    ),
    "135-dual": (
        FiniteInterval(37.0, 39.0),
        FiniteInterval(1.0, 3.0),
        FiniteInterval(2.0, 5.0),
    ),
    "half": (
        FiniteInterval(17.5, 20.5),
        FiniteInterval(-0.5, 2.5),
        FiniteInterval(1.0, 5.0),
    ),
    "xpan": (
        FiniteInterval(66.0, 69.0),
        FiniteInterval(1.0, 4.0),
        FiniteInterval(1.0, 8.0),
    ),
    "120-645": (
        FiniteInterval(46.0, 51.0),
        FiniteInterval(2.0, 7.0),
        FiniteInterval(1.0, 8.0),
    ),
    "120-66": (
        FiniteInterval(58.0, 65.0),
        FiniteInterval(2.0, 9.0),
        FiniteInterval(0.0, 8.0),
    ),
    "120-67": (
        FiniteInterval(72.0, 78.0),
        FiniteInterval(2.0, 8.0),
        FiniteInterval(1.0, 7.0),
    ),
}


def frame_grid_search_prior(
    format_id: str,
    strip_mode: str,
    aperture_long_axis_mm: float,
) -> FrameGridSearchPrior:
    pitch, _catalog_gutter, full_margin = _PRIOR_RANGES[format_id]
    gutter = FiniteInterval(
        pitch.minimum - aperture_long_axis_mm,
        pitch.maximum - aperture_long_axis_mm,
    )
    calibrated = format_id in {"135", "135-dual", "half", "120-66", "120-67"}
    return FrameGridSearchPrior(
        format_id=format_id,
        strip_mode=strip_mode,
        aperture_long_axis_mm=float(aperture_long_axis_mm),
        pitch_mm=pitch,
        gutter_mm=gutter,
        full_leading_margin_mm=full_margin,
        full_trailing_margin_mm=full_margin,
        boundary_uncertainty_mm=3.0,
        equality_interval_mm=0.05,
        calibration_receipt_id=CALIBRATION_RECEIPT_ID,
        provenance=(
            "user_confirmed_geometry" if calibrated else "physical_rule"
        ),
    )
