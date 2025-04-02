## Implemented Changes v2.5a

- lower current-limiting resistors from 470 R to 240 R (see new target)
- emu U32 replace OPA189 by OPA388
- LP for InAmp AD8421 ⇾ 80kHz with 2x 100R, +2x 1nF to GND
- change invNr-Sys to solid white rect
- Emu - use 10mV Ref directly, without Switch
- Rec - use GND as Ref directly
- stabilize 10 mV ⇾ 1uF increase to 2x 10uF, 2R increase to 10R
- replace electrolytic Caps by MLCC (Optionals on Backside)

## Changes and Errors for future Version

- replace target header with 40pin edge-Connector
- keep pin-mapping of target v1.0
- add more dir-changing (reuse 2x Dir of prog-adapter)
- harvester seems a bit too fast - current is overswinging - see SM141K04LV ivcurve
- disable GPIO IO if voltage is cut (due to low_threshold)
- second bat-ok
