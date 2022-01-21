import schemdraw
import schemdraw.elements as elm

elm.style(elm.STYLE_IEC)

drawing = schemdraw.Drawing()
drawing += elm.Dot().label("Input")
drawing += elm.Diode()
S1 = drawing.add(elm.SwitchSpdt().anchor("a").length(2))
boost = drawing.add(elm.VoltageRegulator().label("Boost", "top").anchor("in").at(S1.b))
drawing += elm.Line().down().at(boost.gnd).length(1.5)
drawing += elm.Ground()
drawing += elm.Line().right().length(2).at(boost.out)
N2 = drawing.add(elm.Dot().label("Intermediate"))

drawing += elm.Line().up().length(1).at(S1.c)
drawing += elm.Resistor().right()
drawing += elm.Line().down().length(1.7)
drawing += elm.Dot()

drawing += elm.Capacitor().down().at(N2.start)
drawing += elm.Ground()

drawing += elm.Diode().right().at(N2.start)
S2 = drawing.add(elm.SwitchSpdt().anchor("a").length(2))

buck = drawing.add(elm.VoltageRegulator().label("Buck","top").anchor("in").at(S2.b))
drawing += elm.Line().down().at(buck.gnd).length(1.5)
drawing += elm.Ground()

drawing += elm.Switch().right().at(buck.out)
drawing += elm.Dot().label("Output")

drawing += elm.Line().up().length(1).at(S2.c)
drawing += elm.Line().right()
drawing += elm.Line().down().length(1.7)
drawing += elm.Dot()

drawing.save("32_virtual_source_schemdraw.png")
