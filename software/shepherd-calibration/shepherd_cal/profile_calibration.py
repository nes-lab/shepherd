from typing import Dict
from typing import Optional
from typing import Tuple
from typing import TypeVar
from typing import Union

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy import stats
from shepherd_core import CalibrationPair
from shepherd_core import CalibrationSeries

from .logger import logger

T_calc = TypeVar("T_calc", NDArray[np.float64], float)


class ProfileCalibration(CalibrationSeries):
    @classmethod
    def from_measurement(cls, result: pd.DataFrame):
        values: dict[str, CalibrationPair] = {}
        cal_c = cls._determine_current_cal(result)
        cal_v = cls._determine_voltage_cal(result)
        if cal_c is not None:
            values["current"] = cal_c
        if cal_v is not None:
            values["voltage"] = cal_v
        return cls()

    @staticmethod
    def _measurements_to_calibration(
        ref: pd.Series | float,
        raw: pd.Series | float,
    ) -> tuple[float, float]:
        result = stats.linregress(raw, ref)
        offset = float(result.intercept)
        gain = float(result.slope)
        if result.rvalue < 0.999:
            logger.warning(
                "WARNING: a calibration had a low rvalue = %f",
                result.rvalue,
            )
        return float(gain), float(offset)

    @staticmethod
    def _determine_current_cal(result: pd.DataFrame) -> CalibrationPair | None:
        # chose first voltage above 2.4 V as base, currents range from 60 uA to 14 mA
        result = (
            result.groupby(by=["c_ref_A", "v_shp_V"]).mean().reset_index(drop=False)
        )
        v1 = (
            result[result.v_shp_V >= 2.4]
            .sort_values(by=["v_shp_V"], ignore_index=True)
            .at[0, "v_shp_V"]
        )
        filter0 = (
            (result.c_ref_A >= 60e-6)
            & (result.c_ref_A <= 14e-3)
            & (result.v_shp_V == v1)
        )
        result = result[filter0].reset_index(drop=True)
        if filter0.sum() <= 1:
            logger.warning(
                "NOTE: skipped determining current_calibration (missing data)",
            )
            return None
        try:
            gain, offset = ProfileCalibration._measurements_to_calibration(
                result.c_ref_A,
                result.c_shp_raw,
            )
        except ValueError:
            logger.warning(
                "NOTE: skipped determining current_calibration (failed linregress)",
            )
            return None
        logger.info("  -> resulting C-Cal: gain = %.9f, offset = %f", gain, offset)
        return CalibrationPair(gain=gain, offset=offset)

    @staticmethod
    def _determine_voltage_cal(result: pd.DataFrame) -> CalibrationPair | None:
        # chose first current above 60 uA as base, voltages range from 0.3 V to 2.6 V
        result = (
            result.groupby(by=["c_ref_A", "v_shp_V"]).mean().reset_index(drop=False)
        )
        c1 = (
            result[result.c_ref_A >= 60e-6]
            .sort_values(by=["c_ref_A"], ignore_index=True)
            .at[0, "c_ref_A"]
        )
        filter0 = (
            (result.v_shp_V >= 0.3) & (result.v_shp_V <= 2.6) & (result.c_ref_A == c1)
        )
        result = result[filter0].reset_index(drop=True)
        if filter0.sum() <= 1:
            logger.warning(
                "NOTE: skipped determining voltage_calibration (missing data)",
            )
            return None
        try:
            gain, offset = ProfileCalibration._measurements_to_calibration(
                result.v_ref_V,
                result.v_shp_raw,
            )
        except ValueError:
            logger.warning(
                "NOTE: skipped determining voltage_calibration (failed linregress)",
            )
            return None
        logger.info("  -> resulting V-Cal: gain = %.9f, offset = %f", gain, offset)
        return CalibrationPair(gain=gain, offset=offset)
