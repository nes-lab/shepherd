import pandas as pd
from scipy import stats

from .logger import logger


class Calibration:

    c_gain: float = 1
    c_offset: float = 0
    v_gain: float = 1
    v_offset: float = 0

    def __init__(self):
        pass

    @classmethod
    def from_measurement(cls, result: pd.DataFrame):
        cal = Calibration()
        cal.determine_current_cal(result)
        cal.determine_voltage_cal(result)
        return cal

    @staticmethod
    def measurements_to_calibration(ref, raw) -> tuple:
        result = stats.linregress(raw, ref)
        offset = float(result.intercept)
        gain = float(result.slope)
        if result.rvalue < 0.999:
            logger.warning(
                "WARNING: a calibration had a low rvalue = %f",
                result.rvalue,
            )
        return float(gain), float(offset)

    def determine_current_cal(self, result: pd.DataFrame):
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
            return
        try:
            gain, offset = self.measurements_to_calibration(
                result.c_ref_A,
                result.c_shp_raw,
            )
        except ValueError:
            logger.warning(
                "NOTE: skipped determining current_calibration (failed linregress)",
            )
            return
        logger.info("  -> resulting C-Cal: gain = %.9f, offset = %f", gain, offset)
        self.c_gain, self.c_offset = gain, offset

    def determine_voltage_cal(self, result: pd.DataFrame):
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
            return
        try:
            gain, offset = self.measurements_to_calibration(
                result.v_ref_V,
                result.v_shp_raw,
            )
        except ValueError:
            logger.warning(
                "NOTE: skipped determining voltage_calibration (failed linregress)",
            )
            return
        logger.info("  -> resulting V-Cal: gain = %.9f, offset = %f", gain, offset)
        self.v_gain, self.v_offset = gain, offset

    def convert_current_raw_to_A(self, c_raw):
        return c_raw * self.c_gain + self.c_offset

    def convert_voltage_raw_to_V(self, v_raw):
        return v_raw * self.v_gain + self.v_offset
