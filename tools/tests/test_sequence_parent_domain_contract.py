"""Post-connection proof keeps full measured groups and a common line state.

The context is supplied explicitly to isolate this consumer from pixel
connectivity. Pixel acquisition, original-source checks and guard replay have
their own end-to-end connection tests.
"""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.domain import FiniteInterval,ObservationId,PositiveInterval
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion
from x5crop.detection.photo_geometry.native_trace_bridge_measurement import NativeTraceBridgePeak
from x5crop.detection.photo_geometry import sequence_connections as owner


def peak(coordinate,low=None,high=None):
    return NativeTraceBridgePeak(coordinate,float(coordinate),
        FiniteInterval(coordinate-.5 if low is None else low,coordinate+.5 if high is None else high),
        1,10.,10.,0.,1.)


def assess(region,rows,*,credible_edit=None):
    identity=ObservationId('native:test-parent')
    parent=SimpleNamespace(observation_id=identity,physical_line_region=region,
        canonical_position_px=25.,canonical_direction_degrees=0.,reference_trace_px=0.,
        transition_ids=(ObservationId('raw:a'),ObservationId('raw:b')))
    request=owner.SequenceConnectionRequest(identity,'query:parent',(0,len(rows)),1,None)
    labels=np.zeros((len(rows),64),dtype=np.int32)
    credible=np.zeros_like(labels,dtype=np.uint8)
    for row,peaks in enumerate(rows):
        for p in peaks:
            labels[row,p.source_coordinate_px]=1
            credible[row,int(np.ceil(p.physical_position_interval_px.minimum)):
                int(np.floor(p.physical_position_interval_px.maximum))+1]=1
    if credible_edit is not None:credible_edit(credible)
    strip=SimpleNamespace(trace_start_px=0)
    batch=SimpleNamespace(bound_exceeded=False,plans=(SimpleNamespace(record_peaks=True),))
    measurement=SimpleNamespace(query=SimpleNamespace(query_id='query:parent',
        boundary_axis_scale_px_per_mm=PositiveInterval.exact(20.)))
    with (patch.object(owner,'_connection_context',return_value=(None,labels,credible,(strip,),(0,),(),1,0)),
          patch.object(owner,'peaks_at_row',side_effect=lambda _strip,row:rows[row])):
        return owner._assess_one(parent,request,(measurement,),batch)


class SequenceParentDomainContractTest(unittest.TestCase):
    def test_strictly_outside_branch_cannot_replace_or_expand_parent_but_records_stay_intact(self):
        original=peak(25)
        extra=peak(40)
        rows=((original,),(original,extra),(original,))
        region=PhysicalLineRegion(0.,((24.5,0.),(25.5,0.)))
        result=assess(region,rows)
        self.assertIsNotNone(result.constraint)
        self.assertEqual(result.constraint.trace_position_intervals_px,(original.physical_position_interval_px,)*3)
        self.assertEqual(rows[1],(original,extra))

    def test_two_real_in_domain_branches_remain_competing(self):
        region=PhysicalLineRegion(0.,((19.,0.),(41.,0.)))
        result=assess(region,((peak(20),peak(40)),)*3)
        self.assertIsNone(result.constraint)
        self.assertEqual(result.failure_kind,'dense_peak_competition')

    def test_missing_original_component_peak_is_unavailable_instead_of_multiple_competition(self):
        region=PhysicalLineRegion(0.,((24.5,0.),(25.5,0.)))
        result=assess(region,((peak(25),),(),(peak(25),)))
        self.assertIsNone(result.constraint)
        self.assertEqual(result.failure_kind,'dense_peak_unavailable')

    def test_marginal_intersections_do_not_prove_a_common_line(self):
        region=PhysicalLineRegion(0.,((20.,-.05),(30.,-.05),(30.,.05),(20.,.05)))
        rows=((peak(30),),)+((peak(25),),)*9+((peak(19),),)
        for trace,peaks in enumerate(rows):
            projected=region.project(trace)
            self.assertLessEqual(peaks[0].physical_position_interval_px.minimum,projected.maximum)
            self.assertGreaterEqual(peaks[0].physical_position_interval_px.maximum,projected.minimum)
        result=assess(region,rows)
        self.assertIsNone(result.constraint)
        self.assertEqual(result.failure_kind,'physical_domain_unavailable')

    def test_tangent_and_arithmetic_neighbour_competitors_are_not_excluded(self):
        for delta in (0.,.5e-9):
            region=PhysicalLineRegion(0.,((24.5,0.),(39.5-delta,0.)))
            result=assess(region,((peak(25),peak(40)),)*3)
            self.assertIsNone(result.constraint)
            self.assertEqual(result.failure_kind,'dense_peak_competition')

    def test_complete_group_and_all_query_alias_checks_survive_domain_filter(self):
        region=PhysicalLineRegion(0.,((25.,0.),))
        original=peak(25)
        # An excluded peak whose full interval still aliases the chosen source
        # is rejected by the complete query check, beyond the filtered tuple.
        alias=NativeTraceBridgePeak(40,40.,FiniteInterval(33.5,40.5),1,10.,10.,0.,1.)
        result=assess(region,((peak(34,24.5,35.5),alias),)*3)
        self.assertIsNone(result.constraint)
        self.assertEqual(result.failure_kind,'dense_peak_competition')
        broken=assess(region,((original,peak(40)),)*3,
            credible_edit=lambda mask:mask.__setitem__((1,slice(0,26)),1))
        self.assertIsNone(broken.constraint)
        self.assertEqual(broken.failure_kind,'dense_group_unavailable')

    def test_joint_domain_does_not_clip_full_groups_or_dense_statistical_protection(self):
        region=PhysicalLineRegion(0.,((25.,0.),))
        broad=peak(34,24.5,35.5)
        result=assess(region,((broad,peak(45)),)*3)
        constraint=result.constraint
        self.assertIsNotNone(constraint)
        self.assertEqual(constraint.physical_line_region,region)
        self.assertEqual(constraint.trace_position_intervals_px,(broad.physical_position_interval_px,)*3)
        self.assertGreater(constraint.position_protection_interval_px.maximum,34.)
        self.assertLess(constraint.position_protection_interval_px.minimum,16.)
