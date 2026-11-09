"""Bridge geometry uses the original selector without side-column stand-ins."""
from dataclasses import fields,replace
import unittest

import numpy as np

from tools.tests.test_native_trace_bridge_measurement_contract import _steps
from x5crop.domain import FiniteInterval
from x5crop.detection.photo_geometry import registered_transition_measurement as owner
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC


class TransitionPeakGeometryContractTest(unittest.TestCase):
    def test_minimal_signals_preserve_geometry_and_full_clients_keep_actual_side_statistics(self):
        for values in (_steps()[5],_steps()[9],np.arange(128,dtype=np.uint8)):
            measured=owner.measure_trace(values,FiniteInterval(0.,float(values.size-1)),10.,SPEC,
                                         include_broad_material=False)
            signals=owner.TracePeakSignals(measured.coordinates,measured.gradient_z,measured.tone_z,
                                            measured.texture_z,measured.signed_gradient)
            self.assertFalse(hasattr(signals,'left_tone'))
            for split in (False,True):
                geometry=owner.measured_transition_peak_geometry(signals,SPEC,split_gradient_reversals=split)
                full=owner.measured_transition_peaks(measured,SPEC,split_gradient_reversals=split)
                expected=tuple(owner.TransitionPeakSelection(**{f.name:getattr(p,f.name)
                    for f in fields(owner.TransitionPeakSelection)}) for p in full)
                self.assertEqual(geometry,expected)
                for p in full:
                    for name in ('left_tone','right_tone','left_texture','right_texture'):
                        self.assertEqual(getattr(p,name),float(getattr(measured,name)[p.coordinate_index]))
                if values.size==97:self.assertTrue(full)

    def test_minimal_rows_reject_changed_dtype_and_coordinate_alignment(self):
        coordinates=np.arange(11,dtype=np.int32)
        row=np.zeros(11,dtype=np.float64)
        signals=owner.TracePeakSignals(coordinates,row,row,row,row)
        for changes in ({'gradient_z':row.astype(np.float32)},{'tone_z':row[:-1]},
                        {'signed_gradient':row[None,:]},{'coordinates':coordinates.astype(np.int64)}):
            with self.subTest(changes=tuple(changes)),self.assertRaises(ValueError):
                replace(signals,**changes)
