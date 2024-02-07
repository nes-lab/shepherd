
Umfang:

- 15 Baugruppen / PCBs 
	- wenn möglich 1 PCB Bestückung als Testsample und den Rest 2-3 Wochen später nach Freigabe
	- falls für die letzte Platine wenige Bauteile fehlen, dann gerne unvollständig bestücken
- 350 Bauteile, 50 unique
- einseitige Bestückung
- smallest part: 0402 
- smallest pitch: 0.5 mm
- only top layer populated
- Bestellung notwendig, nicht alle Bauteile konnten beigestellt werden (siehe Unten)

Platinenfertigung / Manufacturing Constraints:

- Designdaten befinden sich im Anhang
    - GerberX2-Datensatz
    - BOM und Packliste für SMD-Teile
    - Pick and Place Koordinaten für SMD-Teile
	- Assembly-Drawings
	- schematics und Platinenrendering

- PCB-Size ist 54.1 x 75.2 mm, 6 Layer
- Koordinatenursprung ist außerhalb des Boards, links unten

- Standard Eurocircuits / Betalayout Designrules
    - 0.15 mm Track Width
    - 0.15 mm Copper Clearance
    - 0.38 mm Edge Clearance
    - 0.35 mm Toolsize / non plated Hole
    - 0.25 mm Plated Hole (End-)Size
    - 0.125 mm Annular Ring
    - 2.54 mm Milling radius
	- beidseitiger Bestückungsdruck
- Stencil: Solder Paste Pads are optimized for a 70 - 110 um Stencil

- markings: 
	- Mech-15 contains assembly notes / Pick and Place 
	- marking origin of part: cross (+) on assembly notes layer 
	- marking pad 1 of ICs: chamfered edge and circle (assembly notes) and filled triangle (silk) 
	- marking cathode of diodes: "C" or chamfered edge (assembly notes) and filled triangle (silk) 
	- Mech-2 contains Top Part Designators 


BOM / Bestellung:

- BOM hat rechts Spalten für Info über beigestellte und fehlende Bauteile
- Bauteile können durch den eigenen Bestand ausgetauscht werden, falls es den Prozess vereinfacht
- fehlende oder nicht ausreichende Bauteile bitte Nachbestellen




Difference in B-Version of v2.4

- adapt to mouser-stock 
	- Pitch: avoid .35 mm , now it's >= 0.5 mm
	- Solder Mask Sliver: now safer > 0.2 mm  
