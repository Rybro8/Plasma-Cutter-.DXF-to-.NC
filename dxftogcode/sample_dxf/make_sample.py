"""Generates a simple test DXF: a rectangle with a circular hole, for smoke-testing the converter."""
import ezdxf

doc = ezdxf.new("R2010")
msp = doc.modelspace()

# Outer rectangle, 100 x 60
msp.add_lwpolyline(
    [(0, 0), (100, 0), (100, 60), (0, 60)], format="xy", close=True
)

# Inner hole
msp.add_circle((30, 30), radius=10)

doc.saveas("rect_with_hole.dxf")
print("wrote rect_with_hole.dxf")
