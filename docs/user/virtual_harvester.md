# Virtual Harvester

:::{note}
TODO: WORK IN PROGRESS
:::

## IVSurface - Transition-Cutout

The analog frontend needs a bit more than a cycle to handle large 5 V transitions.
Solar cells add extra capacitance to the frontend and make the transition slower.

The virtual harvester can cutout these transition periods to avoid recording unwanted capacitive effects.

Using the `cutout_cycles` and `enable_automatic_cutout` parameters is mostly meant to avoid post-processing before using the traces for emulation.
To avoid interfering with the window_size-calculations, this cutout happens at the beginning of the IVCurve-window and will influence V_OC or I_SC values (depending on `rising` parameter).

Automatic mode works by

- gets activated during reset of voltage-ramp
- hold the previous adc-samples during that transition
- check if transition is complete to disable cutout
  (i.e. if rising of voltage stops for a falling ramp)
- compensation for noise via `cutout_cycles`-parameter acting as buffer
  (forgiving that number of cycles that can violate condition before ending the cutout)

### Example 1 - Solar with Rising Ramp

After restarting the voltage ramp (jumping down to 0 V), the current is higher than it should.
As a result, the power-trace has an undesired spike.
This behavior varies with the cell-type and illumination and hints at some capacitive load on the cell.
Note that the 0 V level (I_SC) is lost for this mode, because it is hidden in the transition-period or the cutout.

There is another unwanted effect that raises the Voltage slightly higher when the ramp crosses V_OC.
Due to the design of the harvesting-circuit the recorded voltage shouldn't rise higher than V_OC.

Without cutout:

![iv110-recording without cutout](./media_cutout/hrv_110rn.plot_0s000_to_0s020.png)

With automatic cutout (+3 buffer cycles):

![iv110-recording with automatic cutout](./media_cutout/hrv_110ra.plot_0s000_to_0s020.png)

### Example 2 - Solar with Falling Ramp

After restarting the voltage ramp (jumping up to 5 V), the voltage step is rounded off.
In addition, a small spike can be found in the power-trace.
The transition-phase (or cutout) usually falls in the part of the voltage ramp that is above the V_OC, so no information is lost.

Without cutout:

![iv110-recording without cutout](./media_cutout/hrv_110fn.plot_0s000_to_0s020.png)

With automatic cutout (+3 buffer cycles):

![iv110-recording with automatic cutout](./media_cutout/hrv_110fa.plot_0s000_to_0s020.png)

Note that there is another unwanted effect when the falling voltage ramp crosses V_OC, the current stays lower than expected for the first samples.
