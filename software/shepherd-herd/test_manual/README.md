# Benchmarks

## Harvesting

### From Transducer

hrv_ivcurve                 = 26,846435 mWs

hrv_cv10                    = 24,041531 mWs
hrv_cv20                    = 45,086118 mWs
hrv_mppt_voc                = 55,581604 mWs
hrv_mppt_bq_solar           = 55,279022 mWs
hrv_mppt_bq_thermoelectric  = 43,281144 mWs
hrv_mppt_po                 = 56,171798 mWs
hrv_mppt_opt                = 53,415238 mWs

### From IVCurve C

hrv_ivcurve_cv10_cim                    = 24,061841 mWs
hrv_ivcurve_cv20_cim                    = 45,293206 mWs
hrv_ivcurve_mppt_voc_cim                = 55,781310 mWs
hrv_ivcurve_mppt_bq_solar_cim           = 55,586730 mWs
hrv_ivcurve_mppt_bq_thermoelectric_cim  = 42,805608 mWs
hrv_ivcurve_mppt_po_cim                 = 56,361913 mWs
hrv_ivcurve_mppt_opt_cim                = 57,236651 mWs

### From IVCurve Py

hrv_ivcurve_cv10                    = 24,061841 mWs
hrv_ivcurve_cv20                    = 45,293206 mWs
hrv_ivcurve_mppt_voc                = 55,781310 mWs
hrv_ivcurve_mppt_bq_solar           = 55,586730 mWs
hrv_ivcurve_mppt_bq_thermoelectric  = 42,805609 mWs -> identical, except last digit
hrv_ivcurve_mppt_po                 = 56,361913 mWs
hrv_ivcurve_mppt_opt                = 57,236651 mWs

## Emulation

### Target

hrv_ivcurve_direct_emu      = 237,957013 mWs
hrv_ivcurve_dio_cap_emu     = 51,180749 mWs
hrv_ivcurve_BQ25504_emu     = 50,291193 mWs
hrv_ivcurve_BQ25570_emu     = 47,063520 mWs
hrv_mppt_voc_direct_emu     = 266,889329 mWs
hrv_mppt_voc_dio_cap_emu    = 50,009699 mWs
hrv_mppt_voc_BQ25504_emu    = 50,286746 mWs
hrv_mppt_voc_BQ25570_emu    = 47,044391 mWs
hrv_mppt_po_direct_emu      = 236,746732 mWs
hrv_mppt_po_dio_cap_emu     = 50,187478 mWs
hrv_mppt_po_BQ25504_emu     = 50,754587 mWs
hrv_mppt_po_BQ25570_emu     = 47,554642 mWs

### Simulation C

hrv_ivcurve_direct_cim      = 238,551795 mWs
hrv_ivcurve_dio_cap_cim     = 51,181283 mWs
hrv_ivcurve_BQ25504_cim     = 50,292813 mWs
hrv_ivcurve_BQ25570_cim     = 46,994343 mWs
hrv_mppt_voc_direct_cim     = 267,582445 mWs
hrv_mppt_voc_dio_cap_cim    = 50,011117 mWs
hrv_mppt_voc_BQ25504_cim    = 50,288394 mWs
hrv_mppt_voc_BQ25570_cim    = 47,044898 mWs
hrv_mppt_po_direct_cim      = 237,338993 mWs
hrv_mppt_po_dio_cap_cim     = 50,193853 mWs
hrv_mppt_po_BQ25504_cim     = 50,761248 mWs
hrv_mppt_po_BQ25570_cim     = 47,591982 mWs

### Simulation Py

hrv_ivcurve_direct_sim      = 238,514834 mWs
hrv_ivcurve_dio_cap_sim     = 51,181966 mWs
hrv_ivcurve_BQ25504_sim     = 50,293696 mWs
hrv_ivcurve_BQ25570_sim     = 47,100070 mWs
hrv_mppt_voc_direct_sim     = 267,581982 mWs
hrv_mppt_voc_dio_cap_sim    = 50,011020 mWs
hrv_mppt_voc_BQ25504_sim    = 50,289405 mWs
hrv_mppt_voc_BQ25570_sim    = 47,097267 mWs
hrv_mppt_po_direct_sim      = 237,338342 mWs
hrv_mppt_po_dio_cap_sim     = 50,193663 mWs
hrv_mppt_po_BQ25504_sim     = 50,762194 mWs
hrv_mppt_po_BQ25570_sim     = 47,464787 mWs
