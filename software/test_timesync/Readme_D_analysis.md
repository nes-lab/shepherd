# Prepare Data for the Tool

- Logic 2 Software -> File -> Export Data
- select channels: 1-3 ???
- Time Range: All Time
- Format: CSV
- DON'T use ISO8601 timestamps
- Export and rename file to meaningful description

![logic_export](media/sw_logic2_export.png)

# Analysis

Setup: 

- same cisco switch
- same software configuration
- data recorded with a logic pro 16 @ 500 MHz

## GPIO - Jitter 

How accurate is the 100 ms trigger on different platforms? Lets visualize the jitter of one node.

**BBone Black**

![GPIO-Jitter-BBB](media/analysis_jitter_BBB_023_ABS_HARD_ch0_rising_100ms_jitter.png)

**BBone AI64**

![GPIO-Jitter-BBAI](media/analysis_jitter_AI64_02_ptp_piservo_phc_piservo_ch0_rising_100ms_jitter.png)

**Raspberry Pi CM4**

![GPIO-Jitter-RPiCM4](media/analysis_jitter_CM4_010_cm4_baseline_ch0_rising_100ms_jitter.png)

Some context and final words:
- BBB takes ~ 300 ns to get kernel time. performance looks fine considering the age of the platform
- BBAI takes ~ 40 ns to get kernel time. the random spikes are still unexplained. It could be caused by one of several register-write-locks. The SOC has several co-processors that share the same bus. 
- CM4 was overclocked to match BB-Ai, so it also takes ~ 40 ns to get kernel time. jitter looks best of these three systems

## Sync Performance


**BBone AI64**

![Sync-BBAI](media/analysis_sync_AI64_02_ptp_piservo_phc_piservo_diff_1u2_jitter.png)

**Raspberry Pi CM4**

![Sync-RPiCM4](media/analysis_sync_CM4_005_norm_80_70_diff_1u2_jitter.png)
